import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Evaluations from '@/pages/Evaluations';
import { evaluationsApi, parseDatasetJson, parseReplayOutputs } from '@/api/evaluations';
import { apiClient } from '@/api/client';
import type { DatasetDetail, EvaluationCapabilities, RunComparison, RunDetail } from '@/types/evaluation';

const auth = vi.hoisted(() => ({ user: { id: 'admin-a' }, organizationId: 'org-a', role: 'admin', isLoading: false, isAuthenticated: true }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/components/Layout', () => ({ Layout: ({ children }: { children: ReactNode }) => <main>{children}</main> }));

const output = { text: 'The permit is under review.', citations: [{ source_id: 'permit-1', quote: '' }] };
const dataset: DatasetDetail = {
  id: 'dataset-1', name: 'Synthetic Copilot', description: 'Synthetic fixture, not production evidence.', workflow: 'copilot_answer', created_at: '2026-09-20',
  cases: [{ id: 'case-1', dataset_id: 'dataset-1', created_at: '2026-09-20', name: 'Permit evidence', critical: true,
    input_json: { question: 'What is the status?', example_output: output },
    expected_output: { required_phrases: ['under review'], required_citation_ids: ['permit-1'] },
    retrieved_context: [{ id: 'permit-1', text: 'The permit is under review.', source_url: null }],
  }],
};
const baseline: RunDetail = {
  id: 'baseline-1', dataset_id: dataset.id, mode: 'replay', model: 'fixture', prompt_version: 'example-v1', status: 'completed',
  dataset_fingerprint: 'fingerprint-1', thresholds: { minimum_quality: 0.8 }, summary: { confidence: 0.9, cost_usd: null }, gate_passed: true,
  started_at: '2026-09-20', finished_at: '2026-09-20', results: [{
    id: 'result-1', case_id: 'case-1', case_snapshot: { name: 'Permit evidence', expected_output: { required_phrases: ['under review'] } },
    actual_output: output, retrieved_context: [{ id: 'permit-1', text: 'The permit is under review.' }], status: 'completed', error_code: null,
    model: 'fixture', prompt_version: 'example-v1', latency_ms: 10, tokens_input: null, tokens_output: null, cost_usd: null,
    metrics: { quality: 1, confidence: 0.9, citation_accuracy: 1 },
  }],
};
const candidate: RunDetail = { ...baseline, id: 'candidate-1', prompt_version: 'candidate-v2', gate_passed: false };
const capabilities: EvaluationCapabilities = {
  live_workflows: ['opportunity_memo', 'score_explanation'],
  replay_workflows: ['copilot_answer', 'opportunity_memo', 'multi_agent_research', 'score_explanation'], scorer_version: 'evidence-rubric-v1',
};
const comparison: RunComparison = {
  baseline_id: baseline.id, candidate_id: candidate.id, comparable: true, reasons: [], metric_deltas: { quality: -0.25, confidence: -0.1 },
  regressed_case_ids: ['case-1'], candidate_gate_passed: false, baseline_gate_passed: true,
};

let client: QueryClient;
function mount() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><Evaluations /></QueryClientProvider>);
  return { ...view, switchSession: () => view.rerender(<QueryClientProvider client={client}><Evaluations /></QueryClientProvider>) };
}
async function selectComparison() {
  await screen.findByLabelText('Baseline run');
  fireEvent.change(screen.getByLabelText('Baseline run'), { target: { value: baseline.id } });
  fireEvent.change(screen.getByLabelText('Candidate run'), { target: { value: candidate.id } });
  fireEvent.click(screen.getByRole('button', { name: 'Compare runs' }));
}

beforeEach(() => {
  Object.assign(auth, { user: { id: 'admin-a' }, organizationId: 'org-a', role: 'admin', isLoading: false, isAuthenticated: true });
  vi.spyOn(evaluationsApi, 'datasets').mockResolvedValue([dataset]);
  vi.spyOn(evaluationsApi, 'dataset').mockResolvedValue(dataset);
  vi.spyOn(evaluationsApi, 'capabilities').mockResolvedValue(capabilities);
  vi.spyOn(evaluationsApi, 'runs').mockResolvedValue([]);
  vi.spyOn(evaluationsApi, 'run').mockResolvedValue(baseline);
  vi.spyOn(evaluationsApi, 'createDataset').mockResolvedValue(dataset);
  vi.spyOn(evaluationsApi, 'seedExamples').mockResolvedValue([dataset]);
  vi.spyOn(evaluationsApi, 'startRun').mockResolvedValue(baseline);
  vi.spyOn(evaluationsApi, 'compare').mockResolvedValue(comparison);
});
afterEach(() => { cleanup(); client?.clear(); vi.restoreAllMocks(); });

describe('Evaluation dashboard', () => {
  it.each(['viewer', 'analyst', 'member'])('blocks %s before requesting private data', role => {
    auth.role = role;
    mount();
    expect(screen.getByText('Administrator access is required to view evaluations.')).toBeInTheDocument();
    expect(evaluationsApi.datasets).not.toHaveBeenCalled();
    expect(evaluationsApi.capabilities).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Create dataset' })).not.toBeInTheDocument();
  });

  it('waits for authentication before requesting data', () => {
    auth.isLoading = true;
    mount();
    expect(screen.getByText('Checking access...')).toBeInTheDocument();
    expect(evaluationsApi.datasets).not.toHaveBeenCalled();
  });

  it('shows loading and actionable list errors, then retries', async () => {
    let reject!: (error: Error) => void;
    vi.mocked(evaluationsApi.datasets).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }));
    mount();
    expect(screen.getByText('Loading datasets...')).toBeInTheDocument();
    await act(async () => reject(new Error('Service unavailable')));
    expect(await screen.findByText('Could not load datasets: Service unavailable')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await screen.findByLabelText('Dataset');
  });

  it('seeds examples from the empty state', async () => {
    vi.mocked(evaluationsApi.datasets).mockResolvedValueOnce([]);
    mount();
    await screen.findByText('No evaluation datasets yet');
    fireEvent.click(screen.getByRole('button', { name: 'Seed four synthetic examples' }));
    await screen.findByRole('button', { name: 'Run example replay' });
    expect(evaluationsApi.seedExamples).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['dataset', 'Loading dataset cases...', 'Could not load cases: Offline'],
    ['runs', 'Loading runs...', 'Could not load runs: Offline'],
    ['run', 'Loading run details...', 'Could not load run: Offline'],
  ] as const)('shows %s detail loading and recoverable failures', async (method, loading, message) => {
    let reject!: (error: Error) => void;
    vi.mocked(evaluationsApi.runs).mockResolvedValue([baseline]);
    vi.mocked(evaluationsApi[method]).mockImplementation(() => new Promise<never>((_, fail) => { reject = fail; }));
    mount();
    expect(await screen.findByText(loading)).toBeInTheDocument();
    await act(async () => reject(new Error('Offline')));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('distinguishes explicitly reported zero cost from unknown cost', async () => {
    vi.mocked(evaluationsApi.runs).mockResolvedValue([baseline]);
    vi.mocked(evaluationsApi.run).mockResolvedValue({ ...baseline, results: [{ ...baseline.results[0], cost_usd: 0, tokens_input: 0, tokens_output: 0 }] });
    mount();
    expect(await screen.findByText('$0.000000')).toBeInTheDocument();
    expect(within(screen.getByText('Input tokens').parentElement!).getByText('0')).toBeInTheDocument();
  });

  it('validates dataset JSON and submits the documented example schema', async () => {
    mount();
    const draft = screen.getByLabelText('Dataset JSON');
    const example = (draft as HTMLTextAreaElement).value;
    fireEvent.change(draft, { target: { value: '{broken' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create dataset' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(evaluationsApi.createDataset).not.toHaveBeenCalled();
    fireEvent.change(draft, { target: { value: example } });
    fireEvent.click(screen.getByRole('button', { name: 'Create dataset' }));
    await waitFor(() => expect(evaluationsApi.createDataset).toHaveBeenCalledWith(expect.objectContaining({ workflow: 'copilot_answer', cases: expect.any(Array) }), expect.anything()));
  });

  it('starts a one-click fixture replay and preserves unknown cost and token values', async () => {
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Run example replay' }));
    await waitFor(() => expect(evaluationsApi.startRun).toHaveBeenCalledWith(dataset.id, {
      mode: 'replay', model: 'fixture', prompt_version: 'example-v1', outputs: { 'case-1': output },
    }));
    expect(await screen.findByText('Gate: passed')).toBeInTheDocument();
    expect(screen.getByText('confidence (heuristic)')).toBeInTheDocument();
    for (const label of ['Input tokens', 'Output tokens', 'Cost (USD)']) {
      expect(within(screen.getByText(label).parentElement!).getByText('Unknown')).toBeInTheDocument();
    }
    expect(screen.queryByText('$0.000000')).not.toBeInTheDocument();
    expect(screen.getByText('Actual output')).toBeInTheDocument();
    expect(screen.getByText('Citations')).toBeInTheDocument();
  });

  it('requires explicit replay labels and an exact case ID mapping', async () => {
    mount();
    await screen.findByLabelText('Captured outputs JSON');
    fireEvent.change(screen.getByLabelText('Model label'), { target: { value: 'current' } });
    fireEvent.change(screen.getByLabelText('Prompt version'), { target: { value: 'v2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start run' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('neither named current');
    fireEvent.change(screen.getByLabelText('Model label'), { target: { value: 'captured-model' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start run' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('every case ID');
    expect(evaluationsApi.startRun).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Captured outputs JSON'), { target: { value: JSON.stringify({ 'case-1': output }) } });
    fireEvent.click(screen.getByRole('button', { name: 'Start run' }));
    await waitFor(() => expect(evaluationsApi.startRun).toHaveBeenCalledWith(dataset.id, expect.objectContaining({ model: 'captured-model', prompt_version: 'v2' })));
  });

  it.each(['copilot_answer', 'multi_agent_research'] as const)('never offers live %s even if advertised incorrectly', async workflow => {
    vi.mocked(evaluationsApi.dataset).mockResolvedValue({ ...dataset, workflow });
    vi.mocked(evaluationsApi.capabilities).mockResolvedValue({ ...capabilities, live_workflows: [workflow] });
    mount();
    await screen.findByLabelText('Run mode');
    expect(screen.queryByRole('option', { name: 'Installed live workflow' })).not.toBeInTheDocument();
  });

  it.each(['opportunity_memo', 'score_explanation'] as const)('starts installed %s with fixed labels and no outputs', async workflow => {
    vi.mocked(evaluationsApi.dataset).mockResolvedValue({ ...dataset, workflow });
    mount();
    await screen.findByRole('option', { name: 'Installed live workflow' });
    fireEvent.change(screen.getByLabelText('Run mode'), { target: { value: 'live' } });
    expect(screen.queryByLabelText('Captured outputs JSON')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Start run' }));
    await waitFor(() => expect(evaluationsApi.startRun).toHaveBeenCalledWith(dataset.id, { mode: 'live', model: 'current', prompt_version: 'current' }));
  });

  it('surfaces run failure without fabricating results', async () => {
    vi.mocked(evaluationsApi.startRun).mockRejectedValue(new Error('Runner unavailable'));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Run example replay' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Runner unavailable');
    expect(screen.queryByText('Gate: passed')).not.toBeInTheDocument();
  });

  it('compares compatible runs and reports gate regression', async () => {
    vi.mocked(evaluationsApi.runs).mockResolvedValue([baseline, candidate]);
    mount();
    await selectComparison();
    expect(await screen.findByText('Comparable runs')).toBeInTheDocument();
    expect(evaluationsApi.compare).toHaveBeenCalledWith(baseline.id, candidate.id);
    expect(screen.getByText('Gate regression: baseline passed, candidate did not pass.')).toBeInTheDocument();
    expect(screen.getByText('Regressed cases: case-1')).toBeInTheDocument();
    expect(screen.getByText('-0.250')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Candidate run'), { target: { value: baseline.id } });
    expect(screen.queryByText('Comparable runs')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare runs' })).toBeDisabled();
  });

  it('explains incompatible runs and withholds regression conclusions', async () => {
    vi.mocked(evaluationsApi.runs).mockResolvedValue([baseline, candidate]);
    vi.mocked(evaluationsApi.compare).mockResolvedValue({ ...comparison, comparable: false, reasons: ['Thresholds differ', 'Dataset fingerprint differs'] });
    mount();
    await selectComparison();
    expect(await screen.findByText('Runs are not comparable')).toBeInTheDocument();
    expect(screen.getByText('Thresholds differ')).toBeInTheDocument();
    expect(screen.getByText('Dataset fingerprint differs')).toBeInTheDocument();
    expect(screen.queryByText('-0.250')).not.toBeInTheDocument();
    expect(screen.queryByText(/Gate regression:/)).not.toBeInTheDocument();
  });

  it.each([true, false])('uses the fresh comparison baseline gate instead of stale history (passed=%s)', async baselinePassed => {
    vi.mocked(evaluationsApi.runs).mockResolvedValue([
      { ...baseline, status: 'running', finished_at: null, gate_passed: false }, candidate,
    ]);
    vi.mocked(evaluationsApi.run).mockResolvedValue({ ...baseline, gate_passed: baselinePassed });
    vi.mocked(evaluationsApi.compare).mockResolvedValue({ ...comparison, baseline_gate_passed: baselinePassed });
    mount();
    await screen.findByText(baselinePassed ? 'Gate: passed' : 'Gate: not passed');
    await selectComparison();
    await screen.findByText('Comparable runs');
    expect(screen.getByText('Candidate gate: not passed')).toBeInTheDocument();
    const regression = 'Gate regression: baseline passed, candidate did not pass.';
    const noRegression = 'No pass-to-fail gate regression.';
    expect(screen.getByText(baselinePassed ? regression : noRegression)).toBeInTheDocument();
    expect(screen.queryByText(baselinePassed ? noRegression : regression)).not.toBeInTheDocument();
    expect(evaluationsApi.runs).toHaveBeenCalledTimes(1);
  });

  it('shows comparison loading and errors', async () => {
    let reject!: (error: Error) => void;
    vi.mocked(evaluationsApi.runs).mockResolvedValue([baseline, candidate]);
    vi.mocked(evaluationsApi.compare).mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
    mount();
    await selectComparison();
    expect(screen.getByText('Comparing runs...')).toBeInTheDocument();
    await act(async () => reject(new Error('Comparison unavailable')));
    expect(await screen.findByText('Could not compare runs: Comparison unavailable')).toBeInTheDocument();
  });

  it('disables execution and explains unavailable capabilities', async () => {
    vi.mocked(evaluationsApi.capabilities).mockRejectedValue(new Error('Offline'));
    mount();
    expect(await screen.findByText('Could not load capabilities: Offline')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Run example replay' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Start run' })).toBeDisabled();
  });

  it('discards late dataset responses after a session switch and resets drafts', async () => {
    let finish!: (value: DatasetDetail[]) => void;
    vi.mocked(evaluationsApi.datasets).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValue([]);
    const view = mount();
    fireEvent.change(screen.getByLabelText('Dataset JSON'), { target: { value: 'private draft' } });
    auth.organizationId = 'org-b';
    view.switchSession();
    await screen.findByText('No evaluation datasets yet');
    await act(async () => finish([dataset]));
    expect(screen.queryByText('Synthetic Copilot')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Dataset JSON')).not.toHaveValue('private draft');
  });

  it('does not select or display a late mutation result in the next session', async () => {
    let finish!: (value: RunDetail) => void;
    vi.mocked(evaluationsApi.startRun).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const view = mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Run example replay' }));
    await waitFor(() => expect(evaluationsApi.startRun).toHaveBeenCalledTimes(1));
    auth.user = { id: 'admin-b' };
    vi.mocked(evaluationsApi.datasets).mockResolvedValue([]);
    view.switchSession();
    await screen.findByText('No evaluation datasets yet');
    await act(async () => finish(baseline));
    expect(screen.queryByText('Gate: passed')).not.toBeInTheDocument();
    expect(evaluationsApi.run).not.toHaveBeenCalled();
  });
});

describe('Evaluation contract validation', () => {
  const valid = { name: 'Dataset', workflow: 'score_explanation', cases: [{ name: 'Case', expected_output: { expected_score: 0 } }] };
  it('accepts zero expected score but rejects empty rubrics, extra fields, duplicate evidence, and oversized context', () => {
    expect(parseDatasetJson(JSON.stringify(valid)).cases).toHaveLength(1);
    expect(() => parseDatasetJson(JSON.stringify({ ...valid, unexpected: true }))).toThrow();
    expect(() => parseDatasetJson(JSON.stringify({ ...valid, cases: [{ name: 'Case', expected_output: { forbidden_phrases: ['bad'] } }] }))).toThrow();
    expect(() => parseDatasetJson(JSON.stringify({ ...valid, cases: [{ ...valid.cases[0], retrieved_context: [{ id: 'same', text: 'one' }, { id: 'same', text: 'two' }] }] }))).toThrow();
    expect(() => parseDatasetJson(JSON.stringify({ ...valid, cases: [{ ...valid.cases[0], input_json: { huge: 'a'.repeat(100001) } }] }))).toThrow('100 KB');
  });
  it('rejects negative costs, fractional tokens, unknown fields and wrong case IDs without replacing null usage', () => {
    for (const invalid of [{ cost_usd: -1 }, { tokens_input: 1.2 }, { made_up: true }]) {
      expect(() => parseReplayOutputs(JSON.stringify({ 'case-1': { ...output, ...invalid } }), ['case-1'])).toThrow();
    }
    expect(() => parseReplayOutputs(JSON.stringify({ other: output }), ['case-1'])).toThrow('every case ID');
    expect(parseReplayOutputs(JSON.stringify({ 'case-1': { ...output, cost_usd: null } }), ['case-1'])['case-1'].cost_usd).toBeNull();
  });
  it('uses the API client without duplicating its version prefix', async () => {
    vi.restoreAllMocks();
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue([]);
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue(baseline);
    await evaluationsApi.datasets();
    await evaluationsApi.dataset('id/with slash');
    await evaluationsApi.runs(dataset.id);
    await evaluationsApi.run(baseline.id);
    await evaluationsApi.compare(baseline.id, candidate.id);
    await evaluationsApi.capabilities();
    await evaluationsApi.seedExamples();
    const body = { mode: 'live' as const, model: 'current', prompt_version: 'current' };
    await evaluationsApi.startRun(dataset.id, body);
    expect(get).toHaveBeenCalledWith('/evals/datasets');
    expect(get).toHaveBeenCalledWith('/evals/datasets/id%2Fwith%20slash');
    expect(get).toHaveBeenCalledWith('/evals/runs', { dataset_id: dataset.id });
    expect(get).toHaveBeenCalledWith(`/evals/runs/${baseline.id}`);
    expect(get).toHaveBeenCalledWith('/evals/compare', { baseline_id: baseline.id, candidate_id: candidate.id });
    expect(get).toHaveBeenCalledWith('/evals/capabilities');
    expect(post).toHaveBeenCalledWith('/evals/examples');
    expect(post).toHaveBeenCalledWith(`/evals/datasets/${dataset.id}/runs`, body);
  });
});
