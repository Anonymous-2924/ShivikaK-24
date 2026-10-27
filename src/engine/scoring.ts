// ============================================================================
// Score + letter grade.
// Score is a weighted blend of cash, reputation, company performance, and
// average department morale, then scaled by the game's scoreMultiplier
// (reduced by certain bankruptcy lifelines).
// ============================================================================

import type { GameState } from './types';
import { avgMorale } from './metrics';

// Cash is normalised against a reference "healthy" bankroll so it sits on the
// same 0–100 footing as the other metrics. Tunable here.
const CASH_REFERENCE = 100000;

const WEIGHTS = {
  cash: 0.3,
  reputation: 0.25,
  performance: 0.25,
  morale: 0.2,
};

export function computeScore(state: GameState): number {
  const cashScore = Math.max(
    0,
    Math.min(100, (state.metrics.cash / CASH_REFERENCE) * 100),
  );
  const morale = avgMorale(state.departments);

  const raw =
    cashScore * WEIGHTS.cash +
    state.metrics.reputation * WEIGHTS.reputation +
    state.metrics.performance * WEIGHTS.performance +
    morale * WEIGHTS.morale;

  return Math.round(raw * state.scoreMultiplier);
}

export function letterGrade(score: number): string {
  if (score >= 90) return 'S';
  if (score >= 80) return 'A';
  if (score >= 70) return 'B';
  if (score >= 60) return 'C';
  if (score >= 45) return 'D';
  return 'F';
}

export function gradeBlurb(grade: string, fired: boolean): string {
  if (fired) {
    return 'The board has spoken. Your tenure ends here.';
  }
  switch (grade) {
    case 'S':
      return 'Legendary. They will teach case studies about your run.';
    case 'A':
      return 'Outstanding leadership. Shareholders adore you.';
    case 'B':
      return 'A solid, respectable tenure. The company is in good hands.';
    case 'C':
      return 'Steady but unremarkable. You kept the lights on.';
    case 'D':
      return 'Rocky. The board is watching the exits.';
    default:
      return 'A turbulent reign. History will not be kind.';
  }
}
