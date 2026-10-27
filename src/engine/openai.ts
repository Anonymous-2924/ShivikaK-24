// ============================================================================
// Optional live-AI advice via the OpenAI API.
//
// This is entirely optional. The game is fully playable without a key. If a
// key is set, we ask the model to speak in-character for one advisor. Any
// failure (missing/invalid key, rate limit, network, bad JSON) falls back to
// the built-in rule-based advice — the game never breaks.
//
// The key is read from the Zustand store (persisted in localStorage only) and
// is sent ONLY to api.openai.com.
// ============================================================================

import type { AdvisorDef, GameState, Scenario } from './types';
import { builtInAdvice, type AdvisorAdvice } from './advisors';

export type KeyStatus = 'not-set' | 'valid' | 'invalid' | 'unknown';

function stateSummary(scenario: Scenario, state: GameState): string {
  const depts = state.departments
    .map((d) => `${d.id}: perf ${d.performance}, morale ${d.morale}`)
    .join('; ');
  const opts = scenario.options
    .map((o) => `${o.id} = "${o.label}" (${o.description}, risk ${o.risk})`)
    .join('\n');
  return [
    `Company: cash ${state.metrics.cash}, reputation ${state.metrics.reputation}, performance ${state.metrics.performance}.`,
    `Departments: ${depts}.`,
    `Situation: ${scenario.situation}`,
    `Options:\n${opts}`,
  ].join('\n');
}

/**
 * Get live advice for a single advisor. Returns null on any failure so the
 * caller can fall back to builtInAdvice.
 */
export async function liveAdvice(
  advisor: AdvisorDef,
  scenario: Scenario,
  state: GameState,
  apiKey: string,
  model: string,
): Promise<AdvisorAdvice | null> {
  if (!apiKey) return null;
  const dept = state.departments.find((d) => d.id === advisor.department);
  if (!dept) return null;

  const system = `You are ${advisor.name}, the ${advisor.department} advisor to a CEO. Persona: ${advisor.persona}. Stay strictly in character. You care most about your own department but want the company to survive. Respond ONLY with compact JSON: {"recommendedOptionId": "<one of the option ids>", "text": "<1-2 sentence in-character take>"}.`;
  const user = stateSummary(scenario, state);

  try {
    const res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        temperature: 0.8,
        max_tokens: 160,
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
        response_format: { type: 'json_object' },
      }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    const raw = data?.choices?.[0]?.message?.content;
    if (!raw) return null;
    const parsed = JSON.parse(raw) as {
      recommendedOptionId?: string;
      text?: string;
    };
    const valid = scenario.options.some(
      (o) => o.id === parsed.recommendedOptionId,
    );
    if (!valid || !parsed.text) return null;
    // Reuse built-in expression logic; override text + recommendation.
    const base = builtInAdvice(advisor, scenario, state);
    return {
      ...base,
      recommendedOptionId: parsed.recommendedOptionId!,
      text: parsed.text,
    };
  } catch {
    return null;
  }
}

/** Lightweight key validation by listing models. Returns a status. */
export async function validateKey(apiKey: string): Promise<KeyStatus> {
  if (!apiKey) return 'not-set';
  try {
    const res = await fetch('https://api.openai.com/v1/models', {
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    if (res.ok) return 'valid';
    if (res.status === 401) return 'invalid';
    return 'unknown';
  } catch {
    return 'unknown';
  }
}
