// ============================================================================
// Advisors — expression logic + built-in (rule-based) advice.
//
// Built-in mode works fully offline. Each advisor has a distinct VOICE and
// recommends the option that best serves ITS department, with reasoning tied
// to the actual numbers of that option (cost, revenue, risk, who it helps or
// hurts). The optional live-AI mode lives in ./openai.ts and falls back here.
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
 * situation treats them (the best option available to them).
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

function hash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}

// --- voice banks ------------------------------------------------------------
// Each advisor is assigned ONE style (by their name) so their voice stays
// consistent, while the filler clauses vary per scenario so they don't repeat.

type Tone = 'eager' | 'reluctant' | 'measured';

const STYLES: ((label: string, tone: Tone, pick: number) => string)[] = [
  // Blunt / numbers-first
  (label, tone, pick) =>
    tone === 'eager'
      ? `Numbers don't lie — go with "${label}".`
      : tone === 'reluctant'
        ? `I don't love it, but the math says "${label}".`
        : [`Cold-eyed, "${label}" is the call.`, `On the balance sheet, "${label}" wins.`][pick % 2],
  // Cautious
  (label, tone, pick) =>
    tone === 'eager'
      ? `Carefully now — but yes, "${label}".`
      : tone === 'reluctant'
        ? `This worries me. If we must, "${label}".`
        : [`I'd tread lightly and take "${label}".`, `Measured step: "${label}".`][pick % 2],
  // Enthusiastic
  (label, tone, pick) =>
    tone === 'eager'
      ? [`Honestly? Let's do it — "${label}".`, `No hesitation: "${label}".`][pick % 2]
      : tone === 'reluctant'
        ? `Not my favourite, but "${label}" keeps us moving.`
        : `I lean toward "${label}".`,
  // Analytical
  (label, tone, pick) =>
    tone === 'eager'
      ? `Weighing it all, "${label}" comes out ahead.`
      : tone === 'reluctant'
        ? `Every path has a cost; "${label}" has the least.`
        : [`On balance, "${label}".`, `All told, I'd pick "${label}".`][pick % 2],
  // Skeptical
  (label, tone, pick) =>
    tone === 'eager'
      ? `Against my instincts, "${label}" is actually right.`
      : tone === 'reluctant'
        ? `I'll say it plainly: "${label}" is the lesser evil.`
        : [`If pushed, "${label}".`, `Fine — "${label}".`][pick % 2],
  // Team-first
  (label, tone, pick) =>
    tone === 'eager'
      ? `For the team, "${label}" — they'd rally behind it.`
      : tone === 'reluctant'
        ? `My people won't love it, but "${label}".`
        : [`Thinking of the floor, "${label}".`, `For morale, "${label}".`][pick % 2],
];

/** A clause about the money implications of the pick. */
function moneyClause(o: ScenarioOption): string | null {
  const bits: string[] = [];
  if (o.revenueDelta && o.revenueDelta > 0) bits.push('it grows what we earn every quarter');
  else if (o.revenueDelta && o.revenueDelta < 0) bits.push('it chips away at our revenue');
  if (o.cashChange <= -20000) bits.push("it's a serious cheque to write");
  else if (o.cashChange >= 20000) bits.push('it brings real cash in now');
  if (o.recurring?.some((r) => (r.cashPerQuarter ?? 0) < 0 || (r.revenuePerQuarter ?? 0) < 0))
    bits.push('and it bleeds us for a few quarters');
  return bits.length ? bits.slice(0, 2).join(', ') : null;
}

/** A clause about who the pick helps or hurts, from this advisor's seat. */
function impactClause(o: ScenarioOption, deptId: string, pick: number): string {
  const s = optionScoreForDept(o, deptId);
  if (s >= 6) return ['it plays right to our strengths', 'my team would thrive on it'][pick % 2];
  if (s >= 1) return ['it nudges us forward', 'it helps us a little'][pick % 2];
  if (s <= -6) return ['it will hurt my department', "it's rough on us, I won't pretend otherwise"][pick % 2];
  if (s <= -1) return ['it stings us slightly', "it's not kind to us"][pick % 2];
  return ['it leaves us roughly where we are', "it's neutral for my team"][pick % 2];
}

/** Built-in rule-based advice for one advisor on one scenario. */
export function builtInAdvice(
  advisor: AdvisorDef,
  scenario: Scenario,
  state: GameState,
): AdvisorAdvice {
  const dept = state.departments.find((d) => d.id === advisor.department)!;

  // Rank options by how well they serve this department, lightly tie-broken by
  // company reputation/performance + revenue so advisors aren't purely selfish.
  const ranked = [...scenario.options].sort((a, b) => {
    const score = (o: ScenarioOption) =>
      optionScoreForDept(o, advisor.department) * 3 +
      o.effects.company.reputation +
      o.effects.company.performance +
      (o.revenueDelta ?? 0) / 2000;
    return score(b) - score(a);
  });
  const pick = ranked[0];

  const seed = hash(advisor.name + scenario.id + pick.id);
  const style = STYLES[hash(advisor.name) % STYLES.length];
  const deptScore = optionScoreForDept(pick, advisor.department);
  const tone: Tone = deptScore >= 4 ? 'eager' : deptScore <= -2 ? 'reluctant' : 'measured';

  const opener = style(pick.label, tone, seed);
  const impact = impactClause(pick, advisor.department, seed);
  const money = moneyClause(pick);

  const persona = advisor.persona.split(/[.,]/)[0].trim().toLowerCase();
  // Occasionally lead with a persona reminder so each advisor stays in character.
  const personaLead = seed % 3 === 0 ? `Speaking as someone ${persona} — ` : '';

  const tail = money ? ` ${capitalize(impact)}, and ${money}.` : ` ${capitalize(impact)}.`;
  const text = `${personaLead}${opener}${tail}`;

  return {
    department: advisor.department,
    advisorName: advisor.name,
    expression: expressionFor(dept, scenario),
    recommendedOptionId: pick.id,
    text,
  };
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function allBuiltInAdvice(
  advisors: AdvisorDef[],
  scenario: Scenario,
  state: GameState,
): AdvisorAdvice[] {
  return advisors.map((a) => builtInAdvice(a, scenario, state));
}
