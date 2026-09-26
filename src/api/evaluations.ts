import { z } from 'zod';
import { apiClient } from './client';
import type {
  DatasetCreate, DatasetDetail, DatasetRead, EvalOutput, EvaluationCapabilities,
  JsonValue, RunComparison, RunCreate, RunDetail, RunRead,
} from '@/types/evaluation';

const text = (max: number) => z.string().trim().min(1).max(max);
const score = z.number().finite().min(0).max(100).nullable().optional();
const json: z.ZodType<JsonValue> = z.lazy(() => z.union([
  z.string(), z.number().finite(), z.boolean(), z.null(), z.array(json), z.record(json),
]));
const phrases = z.array(text(1000)).max(50).default([]);
const expectedOutput = z.object({
  required_phrases: phrases, forbidden_phrases: phrases, required_citation_ids: phrases, expected_score: score,
}).strict().refine(value => value.required_phrases.length > 0 || value.required_citation_ids.length > 0 || value.expected_score != null,
  'At least one required phrase, citation, or expected score is required');
const caseSchema = z.object({
  name: text(200), input_json: z.record(json).default({}), expected_output: expectedOutput,
  retrieved_context: z.array(z.object({
    id: text(200), text: text(10000), source_url: z.string().trim().max(2000).nullable().optional(),
  }).strict()).max(100).default([]),
  critical: z.boolean().default(true),
}).strict().refine(value => new Set(value.retrieved_context.map(item => item.id)).size === value.retrieved_context.length,
  'Evidence IDs must be unique within a case');
export const datasetCreateSchema = z.object({
  name: text(200), description: z.string().trim().max(4000).default(''),
  workflow: z.enum(['copilot_answer', 'opportunity_memo', 'multi_agent_research', 'score_explanation']),
  cases: z.array(caseSchema).min(1).max(25),
}).strict();
export const evalOutputSchema = z.object({
  text: text(50000),
  citations: z.array(z.object({ source_id: text(200), quote: z.string().trim().max(2000).default('') }).strict()).max(100).default([]),
  score,
  tokens_input: z.number().int().min(0).max(10000000).nullable().optional(),
  tokens_output: z.number().int().min(0).max(10000000).nullable().optional(),
  cost_usd: z.number().finite().min(0).max(100000).nullable().optional(),
  latency_ms: z.number().finite().min(0).max(86400000).nullable().optional(),
}).strict();

export function parseDatasetJson(value: string): DatasetCreate {
  const result = datasetCreateSchema.parse(JSON.parse(value));
  // Match Python's default ASCII-escaped JSON size, including separator spaces.
  result.cases.forEach((item, index) => {
    const serialized = JSON.stringify({
      ...item,
      expected_output: { ...item.expected_output, expected_score: item.expected_output.expected_score ?? null },
      retrieved_context: item.retrieved_context.map(evidence => ({ ...evidence, source_url: evidence.source_url ?? null })),
    }).replace(/("(?:\\.|[^"\\])*")|([,:])/g, (match, quoted) => quoted ? match : `${match} `)
      .replace(/[\u0080-\uffff]/g, char => `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`);
    if (serialized.length > 100000) throw new Error(`Case ${index + 1} must fit within 100 KB.`);
  });
  return result as DatasetCreate;
}

export function parseReplayOutputs(value: string, caseIds: string[]): Record<string, EvalOutput> {
  const outputs = z.record(evalOutputSchema).parse(JSON.parse(value));
  const ids = Object.keys(outputs);
  if (!ids.length || ids.length > 25 || ids.length !== caseIds.length || caseIds.some(id => !Object.prototype.hasOwnProperty.call(outputs, id))) {
    throw new Error('Provide exactly one captured output for every case ID in this dataset, with no extra IDs.');
  }
  return outputs as Record<string, EvalOutput>;
}

export function evaluationError(error: unknown): string {
  if (error instanceof z.ZodError) return error.issues.map(issue => `${issue.path.join('.') || 'JSON'}: ${issue.message}`).join('; ');
  return error instanceof Error ? error.message : 'The evaluation request failed. Please try again.';
}

export const evaluationsApi = {
  datasets: () => apiClient.get<DatasetRead[]>('/evals/datasets'),
  createDataset: (data: DatasetCreate) => apiClient.post<DatasetDetail>('/evals/datasets', data),
  seedExamples: () => apiClient.post<DatasetRead[]>('/evals/examples'),
  dataset: (id: string) => apiClient.get<DatasetDetail>(`/evals/datasets/${encodeURIComponent(id)}`),
  startRun: (datasetId: string, data: RunCreate) => apiClient.post<RunDetail>(`/evals/datasets/${encodeURIComponent(datasetId)}/runs`, data),
  runs: (datasetId?: string) => apiClient.get<RunRead[]>('/evals/runs', { dataset_id: datasetId }),
  run: (id: string) => apiClient.get<RunDetail>(`/evals/runs/${encodeURIComponent(id)}`),
  compare: (baselineId: string, candidateId: string) => apiClient.get<RunComparison>('/evals/compare', { baseline_id: baselineId, candidate_id: candidateId }),
  capabilities: () => apiClient.get<EvaluationCapabilities>('/evals/capabilities'),
};
