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
import { applyOption, initGameState, settleQuarter } from '../engine/metrics';
import { availableLifelines, pickScenario } from '../engine/scenarioSelection';
import type { KeyStatus } from '../engine/openai';

const SAVE_KEY = 'boardroom.save.v1';
const SETTINGS_KEY = 'boardroom.settings.v1';

const FIRED_SECOND =
  'You drove the company into insolvency a second time. There are no more lifelines — the board has run out of patience.';
const FIRED_NO_LIFELINE =
  'The company is insolvent and your standing is in tatters — no bank, board, or investor will return your calls. There is no way out.';
const CRISIS_REASON =
  'Cash has run dry. The company is insolvent. Choose a lifeline — fast — or this is where your story ends.';

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
  /** Where to resume after a lifeline is taken. */
  crisisReturn: 'decision' | 'review';
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
    const {
      phase,
      game,
      currentScenario,
      pendingLifelines,
      crisisReason,
      firedReason,
      lastLog,
      crisisReturn,
    } = get();
    const snap: Snapshot = {
      phase,
      game,
      currentScenario,
      pendingLifelines,
      crisisReason,
      firedReason,
      lastLog,
      crisisReturn,
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
// Bankruptcy resolution — shared by the immediate decision check and the
// quarter-end settlement check. Mutates `next.bankruptcyCount`.
// ---------------------------------------------------------------------------

type Bankruptcy =
  | { kind: 'ok' }
  | { kind: 'crisis'; lifelines: Scenario[]; reason: string }
  | { kind: 'fired'; reason: string };

function checkBankruptcy(next: GameState, pool: Scenario[]): Bankruptcy {
  if (next.metrics.cash >= 0) return { kind: 'ok' };
  next.bankruptcyCount += 1;
  if (next.bankruptcyCount >= 2) return { kind: 'fired', reason: FIRED_SECOND };
  const lifelines = availableLifelines(next, pool);
  if (lifelines.length === 0) return { kind: 'fired', reason: FIRED_NO_LIFELINE };
  return { kind: 'crisis', lifelines, reason: CRISIS_REASON };
}

// ---------------------------------------------------------------------------
// Decision-advance logic shared by normal decisions and crisis resolution.
// At a quarter boundary it settles revenue (which can itself trigger the
// bankruptcy flow).
// ---------------------------------------------------------------------------

type Advance =
  | { kind: 'decision'; state: GameState; scenario: Scenario }
  | { kind: 'quarter-review'; state: GameState }
  | { kind: 'end'; state: GameState }
  | { kind: 'crisis'; state: GameState; lifelines: Scenario[]; reason: string }
  | { kind: 'fired'; state: GameState; reason: string };

function advanceDecision(
  state: GameState,
  profile: IndustryProfile,
  pool: Scenario[],
): Advance {
  const atQuarterEnd =
    state.decisionInQuarter + 1 >= profile.decisionsPerQuarter;

  if (atQuarterEnd) {
    // Settle the quarter's revenue + recurring effects, then re-check solvency.
    const { next: settled } = settleQuarter(state);
    const b = checkBankruptcy(settled, pool);
    if (b.kind === 'fired') return { kind: 'fired', state: settled, reason: b.reason };
    if (b.kind === 'crisis')
      return { kind: 'crisis', state: settled, lifelines: b.lifelines, reason: b.reason };
    return { kind: 'quarter-review', state: settled };
  }

  const advanced: GameState = {
    ...state,
    decisionInQuarter: state.decisionInQuarter + 1,
  };
  const next = pickScenario(advanced, profile, pool);
  if (!next) return { kind: 'end', state: advanced };
  return { kind: 'decision', state: advanced, scenario: next };
}

// ---------------------------------------------------------------------------

const savedSettings = loadSettings();
const savedSnap = loadSnapshot();

export const useGameStore = create<StoreState>((set, get) => {
  /** Apply an Advance result to the store (shared by decision + lifeline). */
  function applyAdvance(res: Advance, settlementCrisis: boolean) {
    switch (res.kind) {
      case 'decision':
        set({ game: res.state, phase: 'decision', currentScenario: res.scenario });
        break;
      case 'quarter-review':
        set({ game: res.state, phase: 'quarter-review', currentScenario: null });
        break;
      case 'end':
        set({ game: res.state, phase: 'end', currentScenario: null });
        break;
      case 'crisis':
        set({
          game: res.state,
          phase: 'crisis',
          currentScenario: null,
          pendingLifelines: res.lifelines,
          crisisReason: res.reason,
          crisisReturn: settlementCrisis ? 'review' : 'decision',
        });
        break;
      case 'fired':
        set({
          game: res.state,
          phase: 'fired',
          currentScenario: null,
          firedReason: res.reason,
        });
        break;
    }
  }

  return {
    phase: 'industry-select',
    game: null,
    currentScenario: null,
    pendingLifelines: [],
    crisisReason: '',
    firedReason: '',
    lastLog: null,
    crisisReturn: 'decision',
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
      let phase: Phase = 'industry-select';
      if (game) phase = firedReason ? 'fired' : 'decision';
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
        crisisReturn: 'decision',
      });
      persist(get);
    },

    chooseOption: (option) => {
      const { game, currentScenario } = get();
      if (!game || !currentScenario) return;
      const profile = getIndustry(game.industryId)!;
      const pool = getScenarios(game.industryId);

      const { next, deptDeltas, companyDelta, revenueDelta } = applyOption(game, option);
      const log: DecisionLog = {
        quarter: next.quarter,
        scenarioId: currentScenario.id,
        scenarioTitle: currentScenario.title,
        optionId: option.id,
        optionLabel: option.label,
        outcomeText: option.outcomeText,
        cashChange: option.cashChange,
        revenueDelta,
        companyDelta,
        deptDeltas,
      };
      next.history = [...next.history, log];
      next.usedScenarioIds = [...next.usedScenarioIds, currentScenario.id];
      if (option.scoreMultiplierDelta) {
        next.scoreMultiplier = Math.max(0.1, next.scoreMultiplier + option.scoreMultiplierDelta);
      }
      set({ lastLog: log });

      // Immediate (decision-driven) insolvency check.
      const b = checkBankruptcy(next, pool);
      if (b.kind === 'fired') {
        set({ game: next, phase: 'fired', currentScenario: null, firedReason: b.reason });
        persist(get);
        return;
      }
      if (b.kind === 'crisis') {
        set({
          game: next,
          phase: 'crisis',
          currentScenario: null,
          pendingLifelines: b.lifelines,
          crisisReason: b.reason,
          crisisReturn: 'decision',
        });
        persist(get);
        return;
      }

      const res = advanceDecision(next, profile, pool);
      applyAdvance(res, res.kind === 'crisis' || res.kind === 'fired' ? true : false);
      persist(get);
    },

    resolveLifeline: (lifeline, option) => {
      const { game, crisisReturn } = get();
      if (!game) return;
      const profile = getIndustry(game.industryId)!;
      const pool = getScenarios(game.industryId);

      const { next, deptDeltas, companyDelta, revenueDelta } = applyOption(game, option);
      const log: DecisionLog = {
        quarter: next.quarter,
        scenarioId: lifeline.id,
        scenarioTitle: lifeline.title,
        optionId: option.id,
        optionLabel: option.label,
        outcomeText: option.outcomeText,
        cashChange: option.cashChange,
        revenueDelta,
        companyDelta,
        deptDeltas,
      };
      next.history = [...next.history, log];
      next.usedScenarioIds = [...next.usedScenarioIds, lifeline.id];
      if (!next.flags.includes('used_second_chance')) {
        next.flags = [...next.flags, 'used_second_chance'];
      }
      if (option.scoreMultiplierDelta) {
        next.scoreMultiplier = Math.max(0.1, next.scoreMultiplier + option.scoreMultiplierDelta);
      }

      set({ lastLog: log, pendingLifelines: [], crisisReason: '' });

      if (crisisReturn === 'review') {
        // The crisis was caused by quarter-end settlement; the quarter is
        // already settled — show its review.
        set({ game: next, phase: 'quarter-review', currentScenario: null });
      } else {
        const res = advanceDecision(next, profile, pool);
        applyAdvance(res, res.kind === 'crisis' || res.kind === 'fired' ? true : false);
      }
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
        crisisReturn: snap.crisisReturn ?? 'decision',
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
        crisisReturn: 'decision',
        hasSave: false,
      });
    },
  };
});
