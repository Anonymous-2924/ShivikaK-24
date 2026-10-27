// ============================================================================
// Metric math — applying effects, clamping, deriving state.
// ============================================================================

import type {
  CompanyMetrics,
  DepartmentState,
  GameState,
  IndustryProfile,
  QuarterSettlement,
  ScenarioOption,
} from './types';

export const clamp = (v: number, min = 0, max = 100) =>
  Math.max(min, Math.min(max, v));

/** Default starting quarterly revenue if an industry profile omits one. */
export const DEFAULT_START_REVENUE = 8000;

/** Build the initial game state for a freshly chosen industry. */
export function initGameState(profile: IndustryProfile): GameState {
  const metrics: CompanyMetrics = {
    cash: profile.startingState.cash,
    reputation: clamp(profile.startingState.reputation),
    performance: clamp(profile.startingState.performance),
  };
  const departments: DepartmentState[] = profile.departments.map((d) => ({
    id: d.id,
    performance: clamp(d.startPerformance),
    morale: clamp(d.startMorale),
  }));
  return {
    industryId: profile.id,
    metrics,
    departments,
    quarter: 1,
    decisionInQuarter: 0,
    flags: [],
    usedScenarioIds: [],
    bankruptcyCount: 0,
    scoreMultiplier: 1,
    baseRevenue: profile.startingState.revenue ?? DEFAULT_START_REVENUE,
    activeModifiers: [],
    lastSettlement: null,
    history: [],
    quarterStartMetrics: { ...metrics },
    quarterStartDepartments: departments.map((d) => ({ ...d })),
  };
}

/**
 * Apply an option's effects to a game state, mutating a *copy* and returning it
 * along with the exact deltas (post-clamp) for animation/logging. Cash is not
 * clamped — it can go negative (that's what drives the bankruptcy flow).
 */
export function applyOption(
  state: GameState,
  option: ScenarioOption,
): {
  next: GameState;
  deptDeltas: Record<string, { performance: number; morale: number }>;
  companyDelta: { reputation: number; performance: number };
  revenueDelta: number;
} {
  const next: GameState = {
    ...state,
    metrics: { ...state.metrics },
    departments: state.departments.map((d) => ({ ...d })),
    flags: [...state.flags],
    activeModifiers: state.activeModifiers.map((m) => ({ ...m })),
  };

  next.metrics.cash += option.cashChange;

  // Permanent baseline revenue shift (compounds — earned every quarter hence).
  const revenueDelta = option.revenueDelta ?? 0;
  next.baseRevenue = Math.max(0, next.baseRevenue + revenueDelta);

  // Register any time-limited recurring effects.
  for (const r of option.recurring ?? []) {
    if (r.quarters > 0) {
      next.activeModifiers.push({
        label: r.label,
        cashPerQuarter: r.cashPerQuarter ?? 0,
        revenuePerQuarter: r.revenuePerQuarter ?? 0,
        quartersRemaining: r.quarters,
      });
    }
  }

  const repBefore = next.metrics.reputation;
  const perfBefore = next.metrics.performance;
  next.metrics.reputation = clamp(repBefore + option.effects.company.reputation);
  next.metrics.performance = clamp(
    perfBefore + option.effects.company.performance,
  );
  const companyDelta = {
    reputation: next.metrics.reputation - repBefore,
    performance: next.metrics.performance - perfBefore,
  };

  const deptDeltas: Record<string, { performance: number; morale: number }> = {};
  for (const dept of next.departments) {
    const eff = option.effects.departments[dept.id];
    if (!eff) {
      deptDeltas[dept.id] = { performance: 0, morale: 0 };
      continue;
    }
    const pBefore = dept.performance;
    const mBefore = dept.morale;
    dept.performance = clamp(pBefore + eff.performance);
    dept.morale = clamp(mBefore + eff.morale);
    deptDeltas[dept.id] = {
      performance: dept.performance - pBefore,
      morale: dept.morale - mBefore,
    };
  }

  // Apply flags set by this option.
  for (const f of option.setsFlags ?? []) {
    if (!next.flags.includes(f)) next.flags.push(f);
  }

  return { next, deptDeltas, companyDelta, revenueDelta };
}

export const avgMorale = (depts: DepartmentState[]) =>
  depts.reduce((s, d) => s + d.morale, 0) / Math.max(1, depts.length);

export const avgDeptPerformance = (depts: DepartmentState[]) =>
  depts.reduce((s, d) => s + d.performance, 0) / Math.max(1, depts.length);

/**
 * How much the company's quarterly revenue is scaled by how well it is run.
 * Blends company performance with average department performance so good
 * management multiplies income (and bad management shrinks it).
 *   performance 50 / depts 50 -> 1.0x   |   100 -> ~1.4x   |   0 -> ~0.6x
 */
export function performanceMultiplier(state: GameState): number {
  const metric =
    (state.metrics.performance + avgDeptPerformance(state.departments)) / 2;
  return 0.6 + (metric / 100) * 0.8;
}

/**
 * Settle a quarter's finances: credit base revenue (scaled by performance),
 * apply any active recurring effects, then count them down and drop the
 * expired ones. Returns a copy of the state plus a breakdown for display.
 * Cash is not clamped — a heavy recurring drain can push it negative, which
 * the caller feeds into the bankruptcy flow exactly like a decision would.
 */
export function settleQuarter(state: GameState): {
  next: GameState;
  settlement: QuarterSettlement;
} {
  const next: GameState = {
    ...state,
    metrics: { ...state.metrics },
    activeModifiers: state.activeModifiers.map((m) => ({ ...m })),
  };

  const mult = performanceMultiplier(next);
  const grossRevenue = Math.round(next.baseRevenue * mult);

  let modifierCash = 0;
  let modifierRevenue = 0;
  const expired: string[] = [];
  for (const m of next.activeModifiers) {
    modifierCash += m.cashPerQuarter;
    modifierRevenue += m.revenuePerQuarter;
    m.quartersRemaining -= 1;
  }
  for (const m of next.activeModifiers) {
    if (m.quartersRemaining <= 0) expired.push(m.label);
  }
  next.activeModifiers = next.activeModifiers.filter(
    (m) => m.quartersRemaining > 0,
  );

  const netCash = grossRevenue + modifierCash + modifierRevenue;
  next.metrics.cash += netCash;

  const settlement: QuarterSettlement = {
    baseRevenue: next.baseRevenue,
    performanceMultiplier: mult,
    grossRevenue,
    modifierCash,
    modifierRevenue,
    netCash,
    expired,
  };
  next.lastSettlement = settlement;
  return { next, settlement };
}
