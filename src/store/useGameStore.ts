// ============================================================================
// Game store (Zustand) — ties the engine together and drives screen flow.
// Also owns settings (theme, advice mode, OpenAI key) and local persistence.
// ============================================================================

import { create } from 'zustand';
import type {
  DecisionLog,
  GameState,
  IndustryProfile,
  Phase,
  Scenario,
  ScenarioOption,
} from '../engine/types';
import { getIndustry, getScenarios } from '../engine/contentLoader';
import { applyOption, initGameState } from '../engine/metrics';
import { availableLifelines, pickScenario } from '../engine/scenarioSelection';
import type { KeyStatus } from '../engine/openai';

const SAVE_KEY = 'boardroom.save.v1';
const SETTINGS_KEY = 'boardroom.settings.v1';

export type Theme = 'light' | 'dark';
export type AdviceMode = 'builtin' | 'live';

interface Settings {
  theme: Theme;
  adviceMode: AdviceMode;
  openaiKey: string;
  openaiModel: string;
  keyStatus: KeyStatus;
}

interface Snapshot {
  phase: Phase;
  game: GameState | null;
  currentScenario: Scenario | null;
  pendingLifelines: Scenario[];
  crisisReason: string;
  firedReason: string;
  lastLog: DecisionLog | null;
}

interface StoreState extends Snapshot {
  settings: Settings;
  hasSave: boolean;

  // navigation / settings
  setTheme: (t: Theme) => void;
  setAdviceMode: (m: AdviceMode) => void;
  setOpenAiKey: (k: string) => void;
  setOpenAiModel: (m: string) => void;
  setKeyStatus: (s: KeyStatus) => void;
  openSettings: () => void;
  backFromSettings: () => void;

  // game flow
  selectIndustry: (id: string) => void;
  chooseOption: (option: ScenarioOption) => void;
  resolveLifeline: (lifeline: Scenario, option: ScenarioOption) => void;
  advanceAfterQuarterReview: () => void;
  continueSavedGame: () => void;
  newGame: () => void;
}

// ---------------------------------------------------------------------------
// Persistence helpers
// ---------------------------------------------------------------------------

function loadSettings(): Settings {
  const fallback: Settings = {
    theme: 'dark',
    adviceMode: 'builtin',
    openaiKey: '',
    openaiModel: 'gpt-4o-mini',
    keyStatus: 'not-set',
  };
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return fallback;
    return { ...fallback, ...JSON.parse(raw) };
  } catch {
    return fallback;
  }
}

function saveSettings(s: Settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch {
    /* ignore quota / private-mode errors */
  }
}

function loadSnapshot(): Snapshot | null {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Snapshot;
  } catch {
    return null;
  }
}

function persist(get: () => StoreState) {
  try {
    const { phase, game, currentScenario, pendingLifelines, crisisReason, firedReason, lastLog } =
      get();
    const snap: Snapshot = {
      phase,
      game,
      currentScenario,
      pendingLifelines,
      crisisReason,
      firedReason,
      lastLog,
    };
    localStorage.setItem(SAVE_KEY, JSON.stringify(snap));
  } catch {
    /* ignore */
  }
}

/** Apply an industry's theme colors to CSS custom properties. */
export function applyTheme(profile: IndustryProfile) {
  const root = document.documentElement;
  root.style.setProperty('--primary', profile.theme.primary);
  root.style.setProperty('--accent', profile.theme.accent);
  root.style.setProperty('--warn', profile.theme.warn);
}

// ---------------------------------------------------------------------------
// Decision-advance logic shared by normal decisions and crisis resolution.
// Mutates nothing; returns the next phase + scenario for the given state.
// ---------------------------------------------------------------------------

function advanceDecision(
  state: GameState,
  profile: IndustryProfile,
  pool: Scenario[],
): { phase: Phase; nextScenario: Scenario | null; state: GameState } {
  const atQuarterEnd =
    state.decisionInQuarter + 1 >= profile.decisionsPerQuarter;

  if (atQuarterEnd) {
    // End of quarter → review screen. The actual quarter increment happens on
    // advanceAfterQuarterReview so the review can show per-quarter deltas.
    return { phase: 'quarter-review', nextScenario: null, state };
  }

  const advanced: GameState = {
    ...state,
    decisionInQuarter: state.decisionInQuarter + 1,
  };
  const next = pickScenario(advanced, profile, pool) ?? null;
  if (!next) {
    // Ran out of eligible scenarios → gracefully end the run.
    return { phase: 'end', nextScenario: null, state: advanced };
  }
  return { phase: 'decision', nextScenario: next, state: advanced };
}

// ---------------------------------------------------------------------------

const savedSettings = loadSettings();
const savedSnap = loadSnapshot();

export const useGameStore = create<StoreState>((set, get) => ({
  phase: 'industry-select',
  game: null,
  currentScenario: null,
  pendingLifelines: [],
  crisisReason: '',
  firedReason: '',
  lastLog: null,
  settings: savedSettings,
  hasSave: !!(savedSnap && savedSnap.game && savedSnap.phase !== 'industry-select'),

  // -- settings ------------------------------------------------------------
  setTheme: (theme) => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    const settings = { ...get().settings, theme };
    saveSettings(settings);
    set({ settings });
  },
  setAdviceMode: (adviceMode) => {
    const settings = { ...get().settings, adviceMode };
    saveSettings(settings);
    set({ settings });
  },
  setOpenAiKey: (openaiKey) => {
    const settings = { ...get().settings, openaiKey, keyStatus: 'unknown' as KeyStatus };
    saveSettings(settings);
    set({ settings });
  },
  setOpenAiModel: (openaiModel) => {
    const settings = { ...get().settings, openaiModel };
    saveSettings(settings);
    set({ settings });
  },
  setKeyStatus: (keyStatus) => {
    const settings = { ...get().settings, keyStatus };
    saveSettings(settings);
    set({ settings });
  },
  openSettings: () => set({ phase: 'settings' }),
  backFromSettings: () => {
    const { game, firedReason } = get();
    // Return to wherever we were: a live game, an end screen, or the menu.
    let phase: Phase = 'industry-select';
    if (game) {
      if (firedReason) phase = 'fired';
      else phase = 'decision';
    }
    set({ phase });
  },

  // -- game flow -----------------------------------------------------------
  selectIndustry: (id) => {
    const profile = getIndustry(id);
    if (!profile) return;
    applyTheme(profile);
    const game = initGameState(profile);
    const pool = getScenarios(id);
    const scenario = pickScenario(game, profile, pool) ?? null;
    set({
      phase: scenario ? 'decision' : 'end',
      game,
      currentScenario: scenario,
      pendingLifelines: [],
      crisisReason: '',
      firedReason: '',
      lastLog: null,
    });
    persist(get);
  },

  chooseOption: (option) => {
    const { game, currentScenario } = get();
    if (!game || !currentScenario) return;
    const profile = getIndustry(game.industryId)!;
    const pool = getScenarios(game.industryId);

    const { next, deptDeltas, companyDelta } = applyOption(game, option);
    const log: DecisionLog = {
      quarter: next.quarter,
      scenarioId: currentScenario.id,
      scenarioTitle: currentScenario.title,
      optionId: option.id,
      optionLabel: option.label,
      outcomeText: option.outcomeText,
      cashChange: option.cashChange,
      companyDelta,
      deptDeltas,
    };
    next.history = [...next.history, log];
    next.usedScenarioIds = [...next.usedScenarioIds, currentScenario.id];
    if (option.scoreMultiplierDelta) {
      next.scoreMultiplier = Math.max(
        0.1,
        next.scoreMultiplier + option.scoreMultiplierDelta,
      );
    }

    // Bankruptcy check.
    if (next.metrics.cash < 0) {
      const newCount = next.bankruptcyCount + 1;
      next.bankruptcyCount = newCount;

      if (newCount >= 2) {
        set({
          game: next,
          lastLog: log,
          phase: 'fired',
          currentScenario: null,
          firedReason:
            'You drove the company into insolvency a second time. There are no more lifelines — the board has run out of patience.',
        });
        persist(get);
        return;
      }

      const lifelines = availableLifelines(next, pool);
      if (lifelines.length === 0) {
        set({
          game: next,
          lastLog: log,
          phase: 'fired',
          currentScenario: null,
          firedReason:
            'The company is insolvent and your standing is in tatters — no bank, board, or investor will return your calls. There is no way out.',
        });
        persist(get);
        return;
      }

      set({
        game: next,
        lastLog: log,
        phase: 'crisis',
        currentScenario: null,
        pendingLifelines: lifelines,
        crisisReason:
          'Cash has run dry. The company is insolvent. Choose a lifeline — fast — or this is where your story ends.',
      });
      persist(get);
      return;
    }

    // Normal advance.
    const res = advanceDecision(next, profile, pool);
    set({
      game: res.state,
      lastLog: log,
      phase: res.phase,
      currentScenario: res.nextScenario,
    });
    persist(get);
  },

  resolveLifeline: (lifeline, option) => {
    const { game } = get();
    if (!game) return;
    const profile = getIndustry(game.industryId)!;
    const pool = getScenarios(game.industryId);

    const { next, deptDeltas, companyDelta } = applyOption(game, option);
    const log: DecisionLog = {
      quarter: next.quarter,
      scenarioId: lifeline.id,
      scenarioTitle: lifeline.title,
      optionId: option.id,
      optionLabel: option.label,
      outcomeText: option.outcomeText,
      cashChange: option.cashChange,
      companyDelta,
      deptDeltas,
    };
    next.history = [...next.history, log];
    next.usedScenarioIds = [...next.usedScenarioIds, lifeline.id];
    if (!next.flags.includes('used_second_chance')) {
      next.flags = [...next.flags, 'used_second_chance'];
    }
    if (option.scoreMultiplierDelta) {
      next.scoreMultiplier = Math.max(
        0.1,
        next.scoreMultiplier + option.scoreMultiplierDelta,
      );
    }

    // Continue from the decision that caused the crisis.
    const res = advanceDecision(next, profile, pool);
    set({
      game: res.state,
      lastLog: log,
      phase: res.phase,
      currentScenario: res.nextScenario,
      pendingLifelines: [],
      crisisReason: '',
    });
    persist(get);
  },

  advanceAfterQuarterReview: () => {
    const { game } = get();
    if (!game) return;
    const profile = getIndustry(game.industryId)!;
    const pool = getScenarios(game.industryId);

    if (game.quarter >= profile.quartersPerGame) {
      set({ phase: 'end' });
      persist(get);
      return;
    }

    const advanced: GameState = {
      ...game,
      quarter: game.quarter + 1,
      decisionInQuarter: 0,
      quarterStartMetrics: { ...game.metrics },
      quarterStartDepartments: game.departments.map((d) => ({ ...d })),
    };
    const next = pickScenario(advanced, profile, pool) ?? null;
    set({
      game: advanced,
      currentScenario: next,
      phase: next ? 'decision' : 'end',
    });
    persist(get);
  },

  continueSavedGame: () => {
    const snap = loadSnapshot();
    if (!snap || !snap.game) return;
    const profile = getIndustry(snap.game.industryId);
    if (profile) applyTheme(profile);
    set({
      phase: snap.phase,
      game: snap.game,
      currentScenario: snap.currentScenario,
      pendingLifelines: snap.pendingLifelines ?? [],
      crisisReason: snap.crisisReason ?? '',
      firedReason: snap.firedReason ?? '',
      lastLog: snap.lastLog ?? null,
    });
  },

  newGame: () => {
    try {
      localStorage.removeItem(SAVE_KEY);
    } catch {
      /* ignore */
    }
    set({
      phase: 'industry-select',
      game: null,
      currentScenario: null,
      pendingLifelines: [],
      crisisReason: '',
      firedReason: '',
      lastLog: null,
      hasSave: false,
    });
  },
}));
