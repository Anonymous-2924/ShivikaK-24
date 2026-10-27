// ============================================================================
// Content loader
// Scans /content at startup and registers whatever industries + scenarios
// exist. Adding an industry = dropping JSON files in; no engine code changes.
//
// Vite resolves import.meta.glob at build time against the project root (the
// leading "/content" path). Each matched JSON is eagerly imported.
// ============================================================================

import type { IndustryProfile, Scenario } from './types';

const industryModules = import.meta.glob('/content/industries/*.json', {
  eager: true,
}) as Record<string, { default: IndustryProfile }>;

const scenarioModules = import.meta.glob('/content/scenarios/**/*.json', {
  eager: true,
}) as Record<string, { default: Scenario }>;

export interface LoadedContent {
  industries: IndustryProfile[];
  /** Scenarios keyed by industry id. */
  scenariosByIndustry: Record<string, Scenario[]>;
}

function loadContent(): LoadedContent {
  const industries: IndustryProfile[] = Object.values(industryModules).map(
    (m) => m.default,
  );

  const scenariosByIndustry: Record<string, Scenario[]> = {};
  for (const mod of Object.values(scenarioModules)) {
    const s = mod.default;
    if (!s || !s.industry) continue;
    (scenariosByIndustry[s.industry] ??= []).push(s);
  }

  // Deterministic order for the industry grid.
  industries.sort((a, b) => a.name.localeCompare(b.name));

  return { industries, scenariosByIndustry };
}

export const content = loadContent();

export function getIndustry(id: string): IndustryProfile | undefined {
  return content.industries.find((i) => i.id === id);
}

export function getScenarios(industryId: string): Scenario[] {
  return content.scenariosByIndustry[industryId] ?? [];
}
