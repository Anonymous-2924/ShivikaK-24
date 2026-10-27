// ============================================================================
// Metric math — applying effects, clamping, deriving state.
// ============================================================================

import type {
  CompanyMetrics,
  DepartmentState,
  GameState,
  IndustryProfile,
  ScenarioOption,
} from './types';

export const clamp = (v: number, min = 0, max = 100) =>
  Math.max(min, Math.min(max, v));

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
} {
  const next: GameState = {
    ...state,
    metrics: { ...state.metrics },
    departments: state.departments.map((d) => ({ ...d })),
    flags: [...state.flags],
  };

  next.metrics.cash += option.cashChange;

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

  return { next, deptDeltas, companyDelta };
}

export const avgMorale = (depts: DepartmentState[]) =>
  depts.reduce((s, d) => s + d.morale, 0) / Math.max(1, depts.length);

export const avgDeptPerformance = (depts: DepartmentState[]) =>
  depts.reduce((s, d) => s + d.performance, 0) / Math.max(1, depts.length);
