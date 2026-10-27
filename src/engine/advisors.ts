// ============================================================================
// Advisors — expression logic + built-in (rule-based) advice.
//
// Built-in mode works fully offline: each advisor recommends the option that
// best serves ITS department's metrics, wrapped in persona-flavoured text.
// The optional live-AI mode lives in ./openai.ts and falls back to this.
// ============================================================================

import type {
  AdvisorDef,
  DepartmentState,
  Expression,
  GameState,
  Scenario,
  ScenarioOption,
} from './types';

export interface AdvisorAdvice {
  department: string;
  advisorName: string;
  expression: Expression;
  recommendedOptionId: string;
  text: string;
}

/**
 * Expression from a department's current morale, nudged by how the pending
 * situation treats them (the best option available to them). High morale +
 * a good option → happy; low morale or only-bad options → worried/angry.
 */
export function expressionFor(
  dept: DepartmentState,
  scenario: Scenario,
): Expression {
  const bestForDept = Math.max(
    ...scenario.options.map((o) => optionScoreForDept(o, dept.id)),
  );
  const mood = dept.morale + bestForDept * 2;

  if (mood >= 70) return 'happy';
  if (mood >= 45) return 'neutral';
  if (mood >= 25) return 'worried';
  return 'angry';
}

/** How much an option helps a specific department (perf + morale blend). */
function optionScoreForDept(option: ScenarioOption, deptId: string): number {
  const e = option.effects.departments[deptId];
  if (!e) return 0;
  return e.performance * 0.6 + e.morale * 0.4;
}

const OPENERS = [
  'My read:',
  "Here's where I stand —",
  'Speaking for my team,',
  'If you want my honest take,',
];

function hash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** Built-in rule-based advice for one advisor on one scenario. */
export function builtInAdvice(
  advisor: AdvisorDef,
  scenario: Scenario,
  state: GameState,
): AdvisorAdvice {
  const dept = state.departments.find((d) => d.id === advisor.department)!;

  // Rank options by how well they serve this department, lightly tie-broken by
  // company reputation/performance so advisors aren't purely selfish.
  const ranked = [...scenario.options].sort((a, b) => {
    const sa =
      optionScoreForDept(a, advisor.department) * 3 +
      a.effects.company.reputation +
      a.effects.company.performance;
    const sb =
      optionScoreForDept(b, advisor.department) * 3 +
      b.effects.company.reputation +
      b.effects.company.performance;
    return sb - sa;
  });
  const pick = ranked[0];
  const myEffect = pick.effects.departments[advisor.department];
  const helpsMe = myEffect && myEffect.performance + myEffect.morale > 0;

  const opener = OPENERS[hash(advisor.name + scenario.id) % OPENERS.length];
  const personaWord = advisor.persona.split(/[.,]/)[0].toLowerCase();

  const stance = helpsMe
    ? `"${pick.label}" is the right call for us. It plays to our strengths${
        myEffect && myEffect.morale > 3 ? ' and the team would love it' : ''
      }.`
    : `none of these are kind to my department, but "${pick.label}" is the least damaging path I can defend.`;

  const text = `${opener} as someone ${personaWord}, ${stance}`;

  return {
    department: advisor.department,
    advisorName: advisor.name,
    expression: expressionFor(dept, scenario),
    recommendedOptionId: pick.id,
    text,
  };
}

export function allBuiltInAdvice(
  advisors: AdvisorDef[],
  scenario: Scenario,
  state: GameState,
): AdvisorAdvice[] {
  return advisors.map((a) => builtInAdvice(a, scenario, state));
}
