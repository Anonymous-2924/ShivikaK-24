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
  startingState: {
    cash: number;
    reputation: number;
    performance: number;
    /** Starting quarterly revenue (cash earned at each quarter end). */
    revenue?: number;
  };
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

/**
 * A time-limited recurring effect applied once per quarter end, for a fixed
 * number of quarters, then it automatically stops. Use for things like a
 * factory's construction cost (a drain while it's being built) or a scandal
 * that bleeds revenue for a few quarters before the company recovers.
 */
export interface RecurringEffect {
  /** Short label shown in the "Ongoing" list, e.g. "Factory construction". */
  label: string;
  /** Cash applied each quarter (negative = a drain, positive = income). */
  cashPerQuarter?: number;
  /** Revenue added/removed each quarter while active (temporary bump/dip). */
  revenuePerQuarter?: number;
  /** How many quarter-ends it applies for, then it expires. */
  quarters: number;
}

export interface ScenarioOption {
  id: string;
  label: string;
  description: string;
  risk: Risk;
  /** One-time immediate cash change at the moment of the decision. */
  cashChange: number;
  effects: Effects;
  setsFlags?: string[];
  outcomeText: string;
  /**
   * Optional. PERMANENT change to the company's baseline quarterly revenue
   * (e.g. a finished factory raises margins forever: +6000). This compounds —
   * it is earned every quarter from now on. Negative lowers the baseline.
   */
  revenueDelta?: number;
  /**
   * Optional. TIME-LIMITED recurring effects that auto-expire (see
   * RecurringEffect). Distinct from revenueDelta, which is permanent.
   */
  recurring?: RecurringEffect[];
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
  revenueDelta: number;
  companyDelta: { reputation: number; performance: number };
  deptDeltas: Record<string, DeptEffect>;
}

/** A recurring effect currently in force, counting down to expiry. */
export interface ActiveModifier {
  label: string;
  cashPerQuarter: number;
  revenuePerQuarter: number;
  quartersRemaining: number;
}

/** Breakdown of a quarter-end revenue settlement, for the review screen. */
export interface QuarterSettlement {
  baseRevenue: number;
  performanceMultiplier: number;
  grossRevenue: number;
  modifierCash: number;
  modifierRevenue: number;
  /** Net cash credited to the company this quarter (can be negative). */
  netCash: number;
  expired: string[];
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
  /** Permanent baseline quarterly revenue; decisions shift it via revenueDelta. */
  baseRevenue: number;
  /** Time-limited recurring effects currently in force. */
  activeModifiers: ActiveModifier[];
  /** The most recent quarter-end settlement, for the review screen. */
  lastSettlement: QuarterSettlement | null;
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
