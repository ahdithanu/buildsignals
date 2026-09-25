export type ObservabilityDays = 1 | 7 | 30;

export interface ObservabilityOverview {
  generated_at: string;
  window_start: string;
  window_end: string;
  days: number;
  evaluations: {
    runs: number; completed: number; failed: number; running: number;
    gates_passed: number; live_runs: number; replay_runs: number;
    results: number; case_errors: number;
    cost_usd_known: number | null; cost_reported_results: number; cost_unknown_results: number;
    tokens_input_known: number | null; tokens_output_known: number | null;
    tokens_reported_results: number; tokens_unknown_results: number;
    input_tokens_reported_results: number; input_tokens_unknown_results: number;
    output_tokens_reported_results: number; output_tokens_unknown_results: number;
    avg_latency_ms_known: number | null; latency_reported_results: number; latency_unknown_results: number;
    by_workflow: { workflow: string; runs: number; gate_passed: number; failed: number }[];
    daily: { date: string; runs: number; case_errors: number }[];
  };
  ingestion: {
    runs: number; completed: number; partial: number; partial_with_errors: number; failed: number; running: number;
    records_seen: number; records_failed: number; stalled_runs: number;
  };
  attention: { code: string; level: string; summary: string; count: number; href: string }[];
}
