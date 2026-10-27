// ============================================================================
// Boardroom — core type definitions
// The engine is industry-agnostic. Everything specific to an industry lives in
// the /content data files and is described by these types.
// ============================================================================

export type Bucket = 'early' | 'growth' | 'crisis' | 'endgame' | 'bankruptcy';
export type Risk = 'low' | 'medium' | 'high';
export type TagType = 'opportunity' | 'threat' | 'routine' | 'crisis';
export type Expression = 'happy' | 'neutral' | 'worried' | 'angry';

/** A single department definition within an industry profile. */
export interface DepartmentDef {
  id: string;
  name: string;
  icon: string;
  startPerformance: number;
  startMorale: number;
}

/** An advisor attached to a department. */
export interface AdvisorDef {
  department: string;
  name: string;
  persona: string;
  /** Prompt used to generate real portrait art later. Not required at runtime. */
  portraitPrompt?: string;
}

export interface IndustryProfile {
  id: string;
  name: string;
  icon: string;
  tagline: string;
  theme: { primary: string; accent: string; warn: string };
  startingState: { cash: number; reputation: number; performance: number };
  departments: DepartmentDef[];
  advisors: AdvisorDef[];
  quartersPerGame: number;
  decisionsPerQuarter: number;
}

/** Numeric deltas applied to a department when an option is chosen. */
export interface DeptEffect {
  performance: number;
  morale: number;
}

export interface Effects {
  company: { reputation: number; performance: number };
  /** Keyed by department id. Must cover every department of the industry. */
  departments: Record<string, DeptEffect>;
}

export interface MetricCondition {
  metric: 'cash' | 'reputation' | 'performance' | 'score';
  op: '>=' | '<=' | '>' | '<' | '==';
  value: number;
}

export interface Prerequisites {
  minQuarter?: number;
  maxQuarter?: number;
  requiresFlags?: string[];
  excludesFlags?: string[];
  metricConditions?: MetricCondition[];
}

export interface ScenarioOption {
  id: string;
  label: string;
  description: string;
  risk: Risk;
  cashChange: number;
  effects: Effects;
  setsFlags?: string[];
  outcomeText: string;
  /**
   * Optional. Permanently nudges the final-score multiplier when chosen
   * (e.g. an emergency equity raise dilutes ownership: -0.1). Mostly used by
   * `bankruptcy`-bucket lifelines. Omitted = no change.
   */
  scoreMultiplierDelta?: number;
}

export interface Scenario {
  id: string;
  industry: string;
  bucket: Bucket;
  tag: string;
  tagType: TagType;
  title: string;
  situation: string;
  prerequisites: Prerequisites;
  options: ScenarioOption[];
}

// ----------------------------------------------------------------------------
// Live game state
// ----------------------------------------------------------------------------

export interface DepartmentState {
  id: string;
  performance: number;
  morale: number;
}

export interface CompanyMetrics {
  cash: number;
  reputation: number;
  performance: number;
}

/** A record of a resolved decision, for the quarter review + history. */
export interface DecisionLog {
  quarter: number;
  scenarioId: string;
  scenarioTitle: string;
  optionId: string;
  optionLabel: string;
  outcomeText: string;
  cashChange: number;
  companyDelta: { reputation: number; performance: number };
  deptDeltas: Record<string, DeptEffect>;
}

export type Phase =
  | 'industry-select'
  | 'decision'
  | 'quarter-review'
  | 'crisis'
  | 'fired'
  | 'end'
  | 'settings';

export interface GameState {
  industryId: string;
  metrics: CompanyMetrics;
  departments: DepartmentState[];
  quarter: number;
  decisionInQuarter: number; // 0-based index within the current quarter
  flags: string[];
  usedScenarioIds: string[];
  bankruptcyCount: number;
  /** Final-score multiplier, reduced by certain lifelines (e.g. equity raise). */
  scoreMultiplier: number;
  history: DecisionLog[];
  /** Deltas accumulated during the current quarter, for the review screen. */
  quarterStartMetrics: CompanyMetrics;
  quarterStartDepartments: DepartmentState[];
}

/** Result of resolving an option — the computed deltas, for animation. */
export interface ResolveResult {
  log: DecisionLog;
  triggeredBankruptcy: boolean;
}
