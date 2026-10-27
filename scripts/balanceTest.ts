// ============================================================================
// Balance test — simulate random playthroughs to spot broken/overpowered
// scenarios. Run with:  npm run sim  [industryId] [numRuns]
//
// This uses the pure engine functions directly. It loads content from disk
// (the in-app content loader uses Vite's import.meta.glob, which isn't
// available under plain Node, so we read the JSON files ourselves here).
// ============================================================================

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import type {
  IndustryProfile,
  Scenario,
  ScenarioOption,
} from '../src/engine/types';
import { initGameState, applyOption, settleQuarter } from '../src/engine/metrics';
import {
  pickScenario,
  availableLifelines,
} from '../src/engine/scenarioSelection';
import { computeScore, letterGrade } from '../src/engine/scoring';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

function loadIndustry(id: string): IndustryProfile {
  return JSON.parse(
    readFileSync(join(ROOT, 'content/industries', `${id}.json`), 'utf8'),
  );
}

function loadScenarios(id: string): Scenario[] {
  const dir = join(ROOT, 'content/scenarios', id);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => JSON.parse(readFileSync(join(dir, f), 'utf8')) as Scenario);
}

function listIndustries(): string[] {
  const dir = join(ROOT, 'content/industries');
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.replace(/\.json$/, ''));
}

// --- one simulated playthrough ---------------------------------------------

interface RunResult {
  fired: boolean;
  usedSecondChance: boolean;
  quartersSurvived: number;
  score: number;
  grade: string;
  seenScenarioIds: Set<string>;
}

function simulate(profile: IndustryProfile, pool: Scenario[]): RunResult {
  let state = initGameState(profile);
  const seen = new Set<string>();
  let fired = false;

  // Resolve insolvency with a random available lifeline (mirrors the store).
  // Returns true if the run should end in a firing.
  const tryRescue = (): boolean => {
    state.bankruptcyCount += 1;
    if (state.bankruptcyCount >= 2) return true;
    const lifelines = availableLifelines(state, pool);
    if (lifelines.length === 0) return true;
    const ll = lifelines[Math.floor(Math.random() * lifelines.length)];
    seen.add(ll.id);
    const lopt = ll.options[0];
    const { next: afterLL } = applyOption(state, lopt);
    afterLL.usedScenarioIds = [...afterLL.usedScenarioIds, ll.id];
    afterLL.flags = [...afterLL.flags, 'used_second_chance'];
    if (lopt.scoreMultiplierDelta) {
      afterLL.scoreMultiplier = Math.max(0.1, afterLL.scoreMultiplier + lopt.scoreMultiplierDelta);
    }
    state = afterLL;
    return false;
  };

  const maxDecisions = profile.quartersPerGame * profile.decisionsPerQuarter + 5;

  for (let step = 0; step < maxDecisions; step++) {
    const scenario = pickScenario(state, profile, pool);
    if (!scenario) break;
    seen.add(scenario.id);

    const option =
      scenario.options[Math.floor(Math.random() * scenario.options.length)];
    const { next } = applyOption(state, option);
    next.usedScenarioIds = [...next.usedScenarioIds, scenario.id];
    if (option.scoreMultiplierDelta) {
      next.scoreMultiplier = Math.max(0.1, next.scoreMultiplier + option.scoreMultiplierDelta);
    }
    state = next;

    // Immediate (decision-driven) insolvency check.
    if (state.metrics.cash < 0 && tryRescue()) {
      fired = true;
      break;
    }

    // Advance quarter / decision, settling revenue at a quarter boundary.
    if (state.decisionInQuarter + 1 >= profile.decisionsPerQuarter) {
      const { next: settled } = settleQuarter(state);
      state = settled;
      if (state.metrics.cash < 0 && tryRescue()) {
        fired = true;
        break;
      }
      if (state.quarter >= profile.quartersPerGame) break;
      state.quarter += 1;
      state.decisionInQuarter = 0;
    } else {
      state.decisionInQuarter += 1;
    }
  }

  const score = computeScore(state);
  return {
    fired,
    usedSecondChance: state.flags.includes('used_second_chance'),
    quartersSurvived: state.quarter,
    score,
    grade: letterGrade(score),
    seenScenarioIds: seen,
  };
}

// --- dominance check --------------------------------------------------------

function optionValue(o: ScenarioOption) {
  const dept = Object.values(o.effects.departments).reduce(
    (s, e) => s + e.performance + e.morale,
    0,
  );
  // Net recurring over its whole life + the permanent revenue change.
  const recurring = (o.recurring ?? []).reduce(
    (s, r) => s + ((r.cashPerQuarter ?? 0) + (r.revenuePerQuarter ?? 0)) * r.quarters,
    0,
  );
  return {
    cash: o.cashChange,
    rep: o.effects.company.reputation,
    perf: o.effects.company.performance,
    dept,
    revenue: (o.revenueDelta ?? 0) * 3 + recurring,
  };
}

function findDominant(scenario: Scenario): string[] {
  const flags: string[] = [];
  const vals = scenario.options.map(optionValue);
  for (let i = 0; i < scenario.options.length; i++) {
    let dominates = false;
    for (let j = 0; j < scenario.options.length; j++) {
      if (i === j) continue;
      const a = vals[i];
      const b = vals[j];
      const geAll =
        a.cash >= b.cash && a.rep >= b.rep && a.perf >= b.perf && a.dept >= b.dept && a.revenue >= b.revenue;
      const gtOne =
        a.cash > b.cash || a.rep > b.rep || a.perf > b.perf || a.dept > b.dept || a.revenue > b.revenue;
      if (geAll && gtOne) dominates = true;
      else {
        dominates = false;
        break;
      }
    }
    if (dominates && scenario.options.length > 1) {
      flags.push(
        `  ⚠ "${scenario.options[i].label}" strictly dominates the other options in ${scenario.id}`,
      );
    }
  }
  return flags;
}

// --- main -------------------------------------------------------------------

function main() {
  const [, , argId, argRuns] = process.argv;
  const industries = listIndustries();
  const id = argId ?? industries[0];
  const runs = argRuns ? parseInt(argRuns, 10) : 2000;

  if (!industries.includes(id)) {
    console.error(`Unknown industry "${id}". Available: ${industries.join(', ')}`);
    process.exit(1);
  }

  const profile = loadIndustry(id);
  const pool = loadScenarios(id);
  console.log(`\n=== Balance test: ${profile.name} (${runs} runs) ===`);
  console.log(`Scenarios in bank: ${pool.length}\n`);

  // Static dominance analysis.
  const domFlags = pool.flatMap(findDominant);
  if (domFlags.length) {
    console.log('Dominant-option warnings:');
    domFlags.forEach((f) => console.log(f));
    console.log('');
  } else {
    console.log('No strictly-dominant options detected. ✓\n');
  }

  // Simulations.
  let fired = 0;
  let secondChance = 0;
  const grades: Record<string, number> = {};
  const scores: number[] = [];
  let quartersTotal = 0;
  const seenAll = new Set<string>();

  for (let i = 0; i < runs; i++) {
    const r = simulate(profile, pool);
    if (r.fired) fired++;
    if (r.usedSecondChance) secondChance++;
    grades[r.grade] = (grades[r.grade] ?? 0) + 1;
    scores.push(r.score);
    quartersTotal += r.quartersSurvived;
    r.seenScenarioIds.forEach((s) => seenAll.add(s));
  }

  const avg = (a: number[]) => a.reduce((s, x) => s + x, 0) / a.length;
  const pct = (n: number) => `${((n / runs) * 100).toFixed(1)}%`;

  console.log(`Fired:                ${fired} (${pct(fired)})`);
  console.log(`Used second chance:   ${secondChance} (${pct(secondChance)})`);
  console.log(`Avg quarters survived: ${(quartersTotal / runs).toFixed(1)}`);
  console.log(`Avg score:            ${avg(scores).toFixed(1)}`);
  console.log(
    `Score range:          ${Math.min(...scores)} – ${Math.max(...scores)}`,
  );
  console.log('Grade distribution:');
  Object.keys(grades)
    .sort()
    .forEach((g) => console.log(`  ${g}: ${grades[g]} (${pct(grades[g])})`));

  // Coverage: scenarios never selected across all runs.
  const never = pool.filter((s) => !seenAll.has(s.id)).map((s) => s.id);
  if (never.length) {
    console.log(`\n⚠ Never selected in any run (${never.length}):`);
    never.forEach((n) => console.log(`  - ${n}`));
  } else {
    console.log('\nAll scenarios reachable. ✓');
  }
  console.log('');
}

main();
