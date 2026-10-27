// ============================================================================
// Scenario selection — buckets + shuffle + conditional prerequisites.
//
// The engine picks a scenario from the bucket appropriate to the current
// quarter/company state, shuffled, filtered by prerequisites, and never
// repeated within a playthrough. Storyline coherence comes from flags +
// metric conditions on prerequisites.
// ============================================================================

import type { Bucket, GameState, IndustryProfile, Scenario } from './types';
import { computeScore } from './scoring';

/** Fisher–Yates shuffle (pure — operates on a copy). */
export function shuffle<T>(arr: T[], rng: () => number = Math.random): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function metricValue(state: GameState, metric: string): number {
  switch (metric) {
    case 'cash':
      return state.metrics.cash;
    case 'reputation':
      return state.metrics.reputation;
    case 'performance':
      return state.metrics.performance;
    case 'score':
      return computeScore(state);
    default:
      return 0;
  }
}

/** Does the game state satisfy a scenario's prerequisites? */
export function meetsPrerequisites(state: GameState, s: Scenario): boolean {
  const p = s.prerequisites ?? {};
  if (p.minQuarter != null && state.quarter < p.minQuarter) return false;
  if (p.maxQuarter != null && state.quarter > p.maxQuarter) return false;

  for (const f of p.requiresFlags ?? []) {
    if (!state.flags.includes(f)) return false;
  }
  for (const f of p.excludesFlags ?? []) {
    if (state.flags.includes(f)) return false;
  }
  for (const c of p.metricConditions ?? []) {
    const v = metricValue(state, c.metric);
    switch (c.op) {
      case '>=':
        if (!(v >= c.value)) return false;
        break;
      case '<=':
        if (!(v <= c.value)) return false;
        break;
      case '>':
        if (!(v > c.value)) return false;
        break;
      case '<':
        if (!(v < c.value)) return false;
        break;
      case '==':
        if (!(v === c.value)) return false;
        break;
    }
  }
  return true;
}

/**
 * Which non-bankruptcy bucket fits the current quarter + company health?
 * Early game → early; late game → endgame; low health → crisis; else growth.
 */
export function bucketForState(
  state: GameState,
  profile: IndustryProfile,
): Bucket {
  const total = profile.quartersPerGame;
  const q = state.quarter;
  const health =
    state.metrics.performance * 0.5 + state.metrics.reputation * 0.5;
  const lowCash = state.metrics.cash < profile.startingState.cash * 0.3;

  if ((health < 40 || lowCash) && q > 1) return 'crisis';
  if (q <= Math.max(2, Math.ceil(total * 0.25))) return 'early';
  if (q >= Math.ceil(total * 0.75)) return 'endgame';
  return 'growth';
}

/**
 * Pick the next scenario. Tries the preferred bucket first, then falls back to
 * the other non-bankruptcy buckets so play never stalls. Returns undefined
 * only if every eligible scenario has been used.
 */
export function pickScenario(
  state: GameState,
  profile: IndustryProfile,
  pool: Scenario[],
  rng: () => number = Math.random,
): Scenario | undefined {
  const preferred = bucketForState(state, profile);
  const order: Bucket[] = [preferred, 'growth', 'early', 'crisis', 'endgame'];
  const tried = new Set<Bucket>();

  const eligible = (s: Scenario) =>
    s.bucket !== 'bankruptcy' &&
    !state.usedScenarioIds.includes(s.id) &&
    meetsPrerequisites(state, s);

  for (const bucket of order) {
    if (tried.has(bucket)) continue;
    tried.add(bucket);
    const candidates = shuffle(
      pool.filter((s) => s.bucket === bucket && eligible(s)),
      rng,
    );
    if (candidates.length) return candidates[0];
  }

  // Last resort: any eligible scenario regardless of bucket preference.
  const anyLeft = shuffle(pool.filter(eligible), rng);
  return anyLeft[0];
}

/** All currently-available bankruptcy lifelines, filtered by state. */
export function availableLifelines(
  state: GameState,
  pool: Scenario[],
): Scenario[] {
  return pool.filter(
    (s) =>
      s.bucket === 'bankruptcy' &&
      !state.usedScenarioIds.includes(s.id) &&
      meetsPrerequisites(state, s),
  );
}
