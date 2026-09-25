export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type Workflow = 'copilot_answer' | 'opportunity_memo' | 'multi_agent_research' | 'score_explanation';

export interface Evidence { id: string; text: string; source_url?: string | null }
export interface Citation { source_id: string; quote?: string }
export interface ExpectedOutput {
  required_phrases?: string[];
  forbidden_phrases?: string[];
  required_citation_ids?: string[];
  expected_score?: number | null;
}
export interface EvalOutput {
  text: string;
  citations?: Citation[];
  score?: number | null;
  tokens_input?: number | null;
  tokens_output?: number | null;
  cost_usd?: number | null;
  latency_ms?: number | null;
}
export interface CaseCreate {
  name: string;
  input_json?: Record<string, JsonValue>;
  expected_output: ExpectedOutput;
  retrieved_context?: Evidence[];
  critical?: boolean;
}
export interface DatasetCreate {
  name: string;
  description?: string;
  workflow: Workflow;
  cases: CaseCreate[];
}
export interface DatasetRead {
  id: string;
  name: string;
  description: string;
  workflow: Workflow;
  created_at: string;
}
export interface CaseRead extends CaseCreate {
  id: string;
  dataset_id: string;
  created_at: string;
  input_json: Record<string, JsonValue>;
  retrieved_context: Evidence[];
  critical: boolean;
}
export interface DatasetDetail extends DatasetRead { cases: CaseRead[] }
export interface Thresholds {
  minimum_quality: number;
  minimum_citation_accuracy: number;
  minimum_factual_coverage: number;
  maximum_hallucination_risk: number;
}
export interface RunCreate {
  mode: 'live' | 'replay';
  model: string;
  prompt_version: string;
  thresholds?: Thresholds;
  outputs?: Record<string, EvalOutput>;
}
export interface RunRead {
  id: string;
  dataset_id: string;
  mode: string;
  model: string;
  prompt_version: string;
  status: string;
  dataset_fingerprint: string;
  thresholds: Record<string, number>;
  summary: Record<string, JsonValue>;
  gate_passed: boolean;
  started_at: string;
  finished_at: string | null;
}
export interface ResultRead {
  id: string;
  case_id: string;
  case_snapshot: Record<string, JsonValue>;
  actual_output: Record<string, JsonValue> | null;
  retrieved_context: Record<string, JsonValue>[];
  status: string;
  error_code: string | null;
  model: string;
  prompt_version: string;
  latency_ms: number | null;
  tokens_input: number | null;
  tokens_output: number | null;
  cost_usd: number | null;
  metrics: Record<string, number>;
}
export interface RunDetail extends RunRead { results: ResultRead[] }
export interface RunComparison {
  baseline_id: string;
  candidate_id: string;
  comparable: boolean;
  reasons: string[];
  metric_deltas: Record<string, number>;
  regressed_case_ids: string[];
  candidate_gate_passed: boolean;
  baseline_gate_passed: boolean;
}
export interface EvaluationCapabilities {
  live_workflows: Workflow[];
  replay_workflows: Workflow[];
  scorer_version: string;
}
