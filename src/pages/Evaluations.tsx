import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Layout } from '@/components/Layout';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useAuth } from '@/contexts/AuthContext';
import { evaluationError, evaluationsApi, parseDatasetJson, parseReplayOutputs } from '@/api/evaluations';
import type { DatasetDetail, EvaluationCapabilities, RunCreate, RunDetail, RunRead, Workflow } from '@/types/evaluation';

const workflowLabels: Record<Workflow, string> = {
  copilot_answer: 'Copilot answer', opportunity_memo: 'Opportunity memo',
  multi_agent_research: 'Multi-agent research', score_explanation: 'Score explanation',
};
const datasetExample = JSON.stringify({
  name: 'Synthetic evidence check', description: 'Synthetic fixture, not production evidence.', workflow: 'copilot_answer',
  cases: [{
    name: 'Cite the permit', critical: true,
    input_json: { question: 'What is the permit status?' },
    expected_output: { required_phrases: ['under review'], forbidden_phrases: ['approved'], required_citation_ids: ['permit-1'] },
    retrieved_context: [{ id: 'permit-1', text: 'The permit is under review.', source_url: null }],
  }],
}, null, 2);
const selectClass = 'h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm';
const keyFor = (scope: string, ...parts: string[]) => ['evaluations', scope, ...parts];

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <Card className="min-w-0"><CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader><CardContent className="space-y-4">{children}</CardContent></Card>;
}
function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return <div className="min-w-0"><h4 className="mb-1 text-sm font-medium">{label}</h4><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs">{value == null ? 'Unknown / not reported' : JSON.stringify(value, null, 2)}</pre></div>;
}
function Failure({ error }: { error: unknown }) {
  return error ? <p role="alert" className="break-words text-sm text-destructive">{evaluationError(error)}</p> : null;
}
function metricLabel(name: string) {
  const label = name.replace(/_/g, ' ');
  return /confidence/i.test(name) ? `${label} (heuristic)` : label;
}
function Metrics({ values, delta = false }: { values: Record<string, number>; delta?: boolean }) {
  return <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(values).map(([name, value]) => <div key={name} className="rounded-md border p-3"><dt className="text-xs capitalize text-muted-foreground">{metricLabel(name)}</dt><dd className="mt-1 font-mono text-sm">{delta && value > 0 ? '+' : ''}{value.toFixed(3)}</dd></div>)}</dl>;
}

export default function Evaluations() {
  const { user, organizationId, role, isLoading, isAuthenticated } = useAuth();
  const scope = JSON.stringify([user?.id ?? null, organizationId, role]);
  return <Layout><div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
    <header><h1 className="font-display text-xl font-semibold">Evaluations</h1><p className="mt-1 text-sm text-muted-foreground">Evidence regression checks for Build Signals workflows. Admin-only.</p></header>
    {isLoading ? <LoadingState message="Checking access..." /> : !isAuthenticated || role !== 'admin' ? <ErrorState message="Administrator access is required to view evaluations." /> : <EvaluationDashboard key={scope} scope={scope} />}
  </div></Layout>;
}

function EvaluationDashboard({ scope }: { scope: string }) {
  const client = useQueryClient();
  const [datasetId, setDatasetId] = useState('');
  const [draft, setDraft] = useState(datasetExample);
  const [validationError, setValidationError] = useState<unknown>(null);
  const datasetsKey = keyFor(scope, 'datasets');
  const datasets = useQuery({ queryKey: datasetsKey, queryFn: evaluationsApi.datasets, retry: false });
  const capabilities = useQuery({ queryKey: keyFor(scope, 'capabilities'), queryFn: evaluationsApi.capabilities, retry: false });
  const create = useMutation({
    mutationFn: evaluationsApi.createDataset,
    onSuccess: data => {
      client.setQueryData(keyFor(scope, 'dataset', data.id), data);
      void client.invalidateQueries({ queryKey: datasetsKey });
    },
  });
  const seed = useMutation({
    mutationFn: evaluationsApi.seedExamples,
    onSuccess: () => { void client.invalidateQueries({ queryKey: datasetsKey }); },
  });
  const selectedId = datasetId || datasets.data?.[0]?.id || '';
  return <>
    <Panel title="Workflow capabilities">
      {capabilities.isPending ? <LoadingState message="Loading workflow capabilities..." /> : capabilities.error ? <ErrorState message={`Could not load capabilities: ${evaluationError(capabilities.error)}`} onRetry={() => void capabilities.refetch()} /> : <>
        <p className="text-xs text-muted-foreground">Scorer: {capabilities.data.scorer_version}. Confidence metrics are heuristic rubric scores, not calibrated probabilities.</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{Object.entries(workflowLabels).map(([workflow, label]) => <div key={workflow} className="rounded-md border bg-secondary/30 p-3"><p className="text-sm font-medium">{label}</p><p className="mt-1 text-xs text-muted-foreground">{['opportunity_memo', 'score_explanation'].includes(workflow) && capabilities.data.live_workflows.includes(workflow as Workflow) ? 'Installed workflow + captured replay' : 'Captured-output only'}</p></div>)}</div>
        <p className="text-xs text-muted-foreground">Copilot and multi-agent research have no live runner here. Replay evaluates supplied outputs; it does not invoke an LLM.</p>
        <p className="text-xs text-muted-foreground">Citation checks validate source IDs and supplied quotes, not whether every claim is supported. Coverage uses configured phrases and scores; human review is still required.</p>
      </>}
    </Panel>
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <div className="space-y-6">
        <Panel title="Datasets">
          <Button variant="outline" disabled={seed.isPending} onClick={() => seed.mutate(undefined, { onSuccess: data => { if (data[0]) setDatasetId(data[0].id); } })}>{seed.isPending ? 'Seeding examples...' : 'Seed four synthetic examples'}</Button>
          <p className="text-xs text-muted-foreground">Safe to repeat: existing examples are reused.</p>
          <Failure error={seed.error} />
          {datasets.isPending ? <LoadingState message="Loading datasets..." /> : datasets.error ? <ErrorState message={`Could not load datasets: ${evaluationError(datasets.error)}`} onRetry={() => void datasets.refetch()} /> : !datasets.data.length ? <EmptyState title="No evaluation datasets yet" description="Seed synthetic examples or create a dataset below." /> : <>
            <Label htmlFor="dataset">Dataset</Label><select id="dataset" className={selectClass} value={selectedId} onChange={event => setDatasetId(event.target.value)}>{datasets.data.map(item => <option key={item.id} value={item.id}>{item.name} ({workflowLabels[item.workflow]})</option>)}</select>
          </>}
        </Panel>
        <Panel title="Create dataset">
          <form className="space-y-3" onSubmit={event => {
            event.preventDefault(); setValidationError(null); create.reset();
            try { create.mutate(parseDatasetJson(draft), { onSuccess: data => setDatasetId(data.id) }); }
            catch (error) { setValidationError(error); }
          }}>
            <p className="text-xs text-muted-foreground">Use the example schema below. Supply 1-25 cases, unique evidence IDs per case, and at least one required phrase, citation, or expected score per rubric. Unknown fields are rejected.</p>
            <Label htmlFor="dataset-json">Dataset JSON</Label><Textarea id="dataset-json" className="min-h-64 font-mono text-xs" value={draft} onChange={event => setDraft(event.target.value)} spellCheck={false} />
            <details><summary className="cursor-pointer text-sm">View example dataset schema</summary><JsonBlock label="DatasetCreate example" value={JSON.parse(datasetExample)} /></details>
            <Failure error={validationError || create.error} />
            <Button disabled={create.isPending} type="submit">{create.isPending ? 'Creating dataset...' : 'Create dataset'}</Button>
          </form>
        </Panel>
      </div>
      {selectedId ? <DatasetWorkspace key={selectedId} id={selectedId} scope={scope} capabilities={capabilities.error ? undefined : capabilities.data} /> : <EmptyState title="Choose a dataset to inspect cases and runs" />}
    </div>
  </>;
}

function DatasetWorkspace({ id, scope, capabilities }: { id: string; scope: string; capabilities?: EvaluationCapabilities }) {
  const dataset = useQuery({ queryKey: keyFor(scope, 'dataset', id), queryFn: () => evaluationsApi.dataset(id), retry: false });
  return dataset.isPending ? <LoadingState message="Loading dataset cases..." /> : dataset.error ? <ErrorState message={`Could not load cases: ${evaluationError(dataset.error)}`} onRetry={() => void dataset.refetch()} /> : <DatasetRuns dataset={dataset.data} scope={scope} capabilities={capabilities} />;
}

function DatasetRuns({ dataset, scope, capabilities }: { dataset: DatasetDetail; scope: string; capabilities?: EvaluationCapabilities }) {
  const client = useQueryClient();
  const [mode, setMode] = useState<'live' | 'replay'>('replay');
  const [model, setModel] = useState('');
  const [prompt, setPrompt] = useState('');
  const [outputs, setOutputs] = useState('{}');
  const [validationError, setValidationError] = useState<unknown>(null);
  const [runId, setRunId] = useState('');
  const runsKey = keyFor(scope, 'runs', dataset.id);
  const runs = useQuery({ queryKey: runsKey, queryFn: () => evaluationsApi.runs(dataset.id), retry: false });
  const start = useMutation({
    mutationFn: (body: RunCreate) => evaluationsApi.startRun(dataset.id, body),
    onSuccess: data => {
      client.setQueryData(keyFor(scope, 'run', data.id), data);
      void client.invalidateQueries({ queryKey: runsKey });
    },
  });
  const canLive = ['opportunity_memo', 'score_explanation'].includes(dataset.workflow) && !!capabilities?.live_workflows.includes(dataset.workflow);
  const canReplay = !!capabilities?.replay_workflows.includes(dataset.workflow);
  const effectiveMode = canLive ? mode : 'replay';
  const hasExamples = dataset.cases.length > 0 && dataset.cases.every(item => item.input_json.example_output != null);
  const launch = (example: boolean) => {
    setValidationError(null); start.reset();
    try {
      let body: RunCreate;
      if (effectiveMode === 'live' && !example) {
        if (!canLive) throw new Error('Live execution is unavailable for this workflow.');
        body = { mode: 'live', model: 'current', prompt_version: 'current' };
      } else {
        if (!canReplay) throw new Error('Captured replay is unavailable until workflow capabilities are loaded.');
        const modelLabel = example ? 'fixture' : model.trim();
        const promptLabel = example ? 'example-v1' : prompt.trim();
        if (!modelLabel || !promptLabel || modelLabel === 'current' || promptLabel === 'current' || modelLabel.length > 200 || promptLabel.length > 200) throw new Error('Replay requires model and prompt labels (1-200 characters), neither named current.');
        const captured = example ? JSON.stringify(Object.fromEntries(dataset.cases.map(item => [item.id, item.input_json.example_output]))) : outputs;
        body = { mode: 'replay', model: modelLabel, prompt_version: promptLabel, outputs: parseReplayOutputs(captured, dataset.cases.map(item => item.id)) };
      }
      start.mutate(body, { onSuccess: data => setRunId(data.id) });
    } catch (error) { setValidationError(error); }
  };
  const selectedRun = runId || runs.data?.[0]?.id || '';
  return <div className="min-w-0 space-y-6">
    <Panel title={dataset.name}>
      <p className="text-sm text-muted-foreground">{dataset.description}</p>
      <p className="text-xs">{workflowLabels[dataset.workflow]} | {dataset.cases.length} cases | {canLive ? 'Live or captured replay' : 'Captured-output only'}</p>
      {dataset.cases.map(item => <details key={item.id} className="rounded-md border p-3"><summary className="cursor-pointer text-sm font-medium">{item.name} {item.critical ? '(critical)' : '(noncritical)'}</summary><div className="mt-3 space-y-3"><p className="break-all font-mono text-xs">Case ID: {item.id}</p><JsonBlock label="Input" value={item.input_json} /><JsonBlock label="Expected output / rubric" value={item.expected_output} /><JsonBlock label="Retrieved context" value={item.retrieved_context} /></div></details>)}
    </Panel>
    <Panel title="Start evaluation run">
      {hasExamples && <Button variant="outline" disabled={start.isPending || !canReplay} onClick={() => launch(true)}>Run example replay</Button>}
      {hasExamples && <p className="text-xs text-muted-foreground">Uses each case's stored example_output with model fixture and prompt example-v1. No live generation.</p>}
      <form className="space-y-3" onSubmit={event => { event.preventDefault(); launch(false); }}>
        <Label htmlFor="run-mode">Run mode</Label><select id="run-mode" className={selectClass} value={effectiveMode} onChange={event => setMode(event.target.value as 'live' | 'replay')}><option value="replay">Captured-output replay</option>{canLive && <option value="live">Installed live workflow</option>}</select>
        {effectiveMode === 'live' ? <p className="text-sm text-muted-foreground">Runs the installed memo/score implementation, not a configurable LLM. Model and prompt labels are fixed to current. No captured outputs are sent.</p> : <>
          <div className="grid gap-3 sm:grid-cols-2"><div className="space-y-1"><Label htmlFor="model-label">Model label</Label><Input id="model-label" required maxLength={200} placeholder="e.g. captured-model-v2" value={model} onChange={event => setModel(event.target.value)} /></div><div className="space-y-1"><Label htmlFor="prompt-label">Prompt version</Label><Input id="prompt-label" required maxLength={200} placeholder="e.g. evidence-prompt-v3" value={prompt} onChange={event => setPrompt(event.target.value)} /></div></div>
          <Label htmlFor="outputs-json">Captured outputs JSON</Label><Textarea id="outputs-json" className="min-h-40 font-mono text-xs" value={outputs} onChange={event => setOutputs(event.target.value)} spellCheck={false} />
          <details><summary className="cursor-pointer text-sm">View output mapping schema and case IDs</summary><JsonBlock label="EvalOutput mapping example (replace with captured outputs)" value={Object.fromEntries(dataset.cases.map(item => [item.id, { text: 'Replace with the captured answer.', citations: [{ source_id: item.retrieved_context[0]?.id ?? 'source-id', quote: '' }], score: null, tokens_input: null, tokens_output: null, cost_usd: null, latency_ms: null }]))} /></details>
        </>}
        <p className="text-xs text-muted-foreground">Default gate: quality and factual coverage at least 0.8, citation accuracy at least 1.0, hallucination risk at most 0.0. Confidence scores are heuristic.</p>
        <Failure error={validationError || start.error} />
        <Button type="submit" disabled={start.isPending || (effectiveMode === 'live' ? !canLive : !canReplay)}>{start.isPending ? 'Running evaluation...' : 'Start run'}</Button>
      </form>
    </Panel>
    <Panel title="Run history">
      <Button size="sm" variant="outline" disabled={runs.isFetching} onClick={() => void runs.refetch()}>Refresh runs</Button>
      {runs.isPending ? <LoadingState message="Loading runs..." /> : runs.error ? <ErrorState message={`Could not load runs: ${evaluationError(runs.error)}`} onRetry={() => void runs.refetch()} /> : !runs.data.length ? <EmptyState title="No runs yet" /> : <><Label htmlFor="inspect-run">Inspect run</Label><select id="inspect-run" className={selectClass} value={selectedRun} onChange={event => setRunId(event.target.value)}>{runs.data.map(run => <option key={run.id} value={run.id}>{runLabel(run)}</option>)}</select></>}
    </Panel>
    {selectedRun && <RunInspector key={selectedRun} id={selectedRun} scope={scope} />}
    {!!runs.data?.length && <CompareRuns scope={scope} runs={runs.data} />}
  </div>;
}

function runLabel(run: RunRead) {
  return `${run.model} / ${run.prompt_version} | ${run.mode} | ${run.status} | ${run.id}`;
}
function RunInspector({ id, scope }: { id: string; scope: string }) {
  const run = useQuery({ queryKey: keyFor(scope, 'run', id), queryFn: () => evaluationsApi.run(id), retry: false,
    refetchInterval: query => query.state.data && ['pending', 'queued', 'running'].includes(query.state.data.status) ? 2000 : false,
  });
  return <Panel title="Run inspection">{run.isPending ? <LoadingState message="Loading run details..." /> : run.error ? <ErrorState message={`Could not load run: ${evaluationError(run.error)}`} onRetry={() => void run.refetch()} /> : <RunResults run={run.data} />}</Panel>;
}
function RunResults({ run }: { run: RunDetail }) {
  return <>
    <p className="break-words text-sm">{runLabel(run)}</p>
    <p className={run.gate_passed ? 'font-medium text-emerald-700' : 'font-medium text-destructive'}>Gate: {run.gate_passed ? 'passed' : 'not passed'}</p>
    <p className="break-all text-xs text-muted-foreground">Dataset fingerprint: {run.dataset_fingerprint}</p>
    <p className="text-xs text-muted-foreground">Confidence metrics are heuristic, not calibrated probabilities. Null usage is unknown, never zero.</p>
    <JsonBlock label="Run summary (confidence values are heuristic; null = unknown)" value={run.summary} />
    <details><summary className="cursor-pointer text-sm">Gate thresholds</summary><JsonBlock label="Thresholds" value={run.thresholds} /></details>
    {!run.results.length && <p className="text-sm text-muted-foreground">No case results reported yet.</p>}
    {run.results.map(result => <article key={result.id} className="space-y-4 rounded-lg border p-4">
      <h4 className="break-words font-medium">{typeof result.case_snapshot.name === 'string' ? result.case_snapshot.name : result.case_id}</h4>
      <p className="break-all text-xs">Case {result.case_id} | {result.status} | {result.model} / {result.prompt_version}</p>
      {result.error_code && <p role="alert" className="text-sm text-destructive">Case error: {result.error_code}</p>}
      <div className="grid gap-3 sm:grid-cols-2"><JsonBlock label="Expected output / rubric" value={result.case_snapshot.expected_output} /><JsonBlock label="Actual output" value={result.actual_output} /><JsonBlock label="Retrieved context" value={result.retrieved_context} /><JsonBlock label="Citations" value={result.actual_output?.citations} /></div>
      <details><summary className="cursor-pointer text-sm">Case snapshot / input</summary><JsonBlock label="Case snapshot" value={result.case_snapshot} /></details>
      <h5 className="text-sm font-medium">Metric scores</h5><Metrics values={result.metrics} />
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4"><div><dt className="text-xs text-muted-foreground">Input tokens</dt><dd>{result.tokens_input ?? 'Unknown'}</dd></div><div><dt className="text-xs text-muted-foreground">Output tokens</dt><dd>{result.tokens_output ?? 'Unknown'}</dd></div><div><dt className="text-xs text-muted-foreground">Cost (USD)</dt><dd>{result.cost_usd == null ? 'Unknown' : `$${result.cost_usd.toFixed(6)}`}</dd></div><div><dt className="text-xs text-muted-foreground">Latency (ms)</dt><dd>{result.latency_ms ?? 'Unknown'}</dd></div></dl>
    </article>)}
  </>;
}

function CompareRuns({ scope, runs }: { scope: string; runs: RunRead[] }) {
  const [baseline, setBaseline] = useState('');
  const [candidate, setCandidate] = useState('');
  const [pair, setPair] = useState<[string, string] | null>(null);
  const comparison = useQuery({ queryKey: keyFor(scope, 'compare', pair?.[0] ?? '', pair?.[1] ?? ''), queryFn: () => evaluationsApi.compare(pair![0], pair![1]), enabled: !!pair, retry: false });
  return <Panel title="Compare runs">
    <p className="text-xs text-muted-foreground">Choose two runs from this dataset. The server checks fingerprint, scorer, and threshold compatibility before comparing candidate minus baseline.</p>
    <div className="grid gap-3 sm:grid-cols-2">{(['Baseline', 'Candidate'] as const).map(label => <div key={label} className="space-y-1"><Label htmlFor={`compare-${label}`}>{label} run</Label><select id={`compare-${label}`} className={selectClass} value={label === 'Baseline' ? baseline : candidate} onChange={event => { setPair(null); if (label === 'Baseline') setBaseline(event.target.value); else setCandidate(event.target.value); }}><option value="">Select a run</option>{runs.map(run => <option key={run.id} value={run.id}>{runLabel(run)}</option>)}</select></div>)}</div>
    <Button variant="outline" disabled={!baseline || !candidate || baseline === candidate || comparison.isFetching} onClick={() => setPair([baseline, candidate])}>Compare runs</Button>
    {baseline && baseline === candidate && <p className="text-sm text-muted-foreground">Choose two different runs.</p>}
    {pair && (comparison.isPending ? <LoadingState message="Comparing runs..." /> : comparison.error ? <ErrorState message={`Could not compare runs: ${evaluationError(comparison.error)}`} onRetry={() => void comparison.refetch()} /> : comparison.data && <div className="space-y-3" aria-live="polite">
      <p className="font-medium">{comparison.data.comparable ? 'Comparable runs' : 'Runs are not comparable'}</p>
      {!!comparison.data.reasons.length && <ul className="list-inside list-disc text-sm">{comparison.data.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>}
      <p className={comparison.data.candidate_gate_passed ? 'text-emerald-700' : 'text-destructive'}>Candidate gate: {comparison.data.candidate_gate_passed ? 'passed' : 'not passed'}</p>
      {comparison.data.comparable ? <>
        <p className="text-sm">{comparison.data.baseline_gate_passed && !comparison.data.candidate_gate_passed ? 'Gate regression: baseline passed, candidate did not pass.' : 'No pass-to-fail gate regression.'}</p>
        <p className="text-xs text-muted-foreground">Metric deltas are candidate minus baseline, not a universal improvement score. Lower hallucination risk is better; confidence metrics are heuristic.</p>
        <Metrics values={comparison.data.metric_deltas} delta />
        <p className="break-words text-sm">Regressed cases: {comparison.data.regressed_case_ids.length ? comparison.data.regressed_case_ids.join(', ') : 'None'}</p>
      </> : <p className="text-sm text-muted-foreground">Regression conclusions and metric deltas are withheld for incompatible runs.</p>}
    </div>)}
  </Panel>;
}
