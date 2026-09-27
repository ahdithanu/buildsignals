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
import { promptsApi } from '@/api/prompts';
import type { CreateTemplate, PromptContent, TemplateDetail } from '@/types/prompts';

const selectClass = 'h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm';
const keyFor = (scope: string, ...parts: (string | number)[]) => ['prompts', scope, ...parts];
const message = (error: unknown) => error instanceof Error ? error.message : 'The request failed. Please try again.';
const variablesFrom = (value: string) => value.split(',').map(part => part.trim()).filter(Boolean);

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <Card className="min-w-0"><CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader><CardContent className="space-y-4">{children}</CardContent></Card>;
}
function Failure({ error }: { error: unknown }) {
  return error ? <p role="alert" className="break-words text-sm text-destructive">{message(error)}</p> : null;
}

export default function PromptRegistry() {
  const { user, organizationId, role, isLoading, isAuthenticated } = useAuth();
  const scope = JSON.stringify([user?.id ?? null, organizationId, role]);
  return <Layout><div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
    <header><h1 className="font-display text-xl font-semibold">Prompt registry</h1><p className="mt-1 text-sm text-muted-foreground">Versioned workspace templates. Admin-only.</p></header>
    {isLoading ? <LoadingState message="Checking access..." /> : !isAuthenticated || role !== 'admin' || !organizationId ? <ErrorState message="Administrator access is required to view prompts." /> : <Registry key={scope} scope={scope} />}
  </div></Layout>;
}

function Registry({ scope }: { scope: string }) {
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState('');
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [workflow, setWorkflow] = useState('');
  const [description, setDescription] = useState('');
  const [body, setBody] = useState('');
  const [variables, setVariables] = useState('');
  const listKey = keyFor(scope, 'list');
  const list = useQuery({ queryKey: listKey, queryFn: promptsApi.list, retry: false });
  const create = useMutation({ mutationFn: promptsApi.create, onSuccess: detail => {
    client.setQueryData(keyFor(scope, 'detail', detail.id), detail);
    void client.invalidateQueries({ queryKey: listKey });
    setSelectedId(detail.id);
    setKey(''); setName(''); setWorkflow(''); setDescription(''); setBody(''); setVariables('');
  } });
  const currentId = selectedId || list.data?.[0]?.id || '';
  return <>
    <p className="border-l-2 border-foreground bg-secondary/40 p-3 text-xs">Activation only selects a registry version. It does not alter the deterministic memo/scoring workflow or invoke an LLM. Preview only renders supplied values.</p>
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <div className="space-y-6">
        <Panel title="Templates">
          {list.isPending ? <LoadingState message="Loading templates..." /> : list.error ? <ErrorState message={`Could not load templates: ${message(list.error)}`} onRetry={() => void list.refetch()} /> : !list.data.length ? <EmptyState title="No prompt templates yet" /> : <><Label htmlFor="template">Template</Label><select id="template" className={selectClass} value={currentId} onChange={event => setSelectedId(event.target.value)}>{list.data.map(item => <option key={item.id} value={item.id}>{item.name} ({item.key})</option>)}</select><p className="text-xs text-muted-foreground">{list.data.length} workspace templates</p></>}
        </Panel>
        <Panel title="Create template">
          <form className="space-y-3" onSubmit={event => { event.preventDefault(); create.mutate({ key: key.trim(), name: name.trim(), workflow: workflow.trim(), description: description.trim(), body, variables: variablesFrom(variables) } satisfies CreateTemplate); }}>
            <div className="grid gap-3 sm:grid-cols-2"><div><Label htmlFor="prompt-key">Key</Label><Input id="prompt-key" required value={key} onChange={event => setKey(event.target.value)} /></div><div><Label htmlFor="prompt-name">Name</Label><Input id="prompt-name" required value={name} onChange={event => setName(event.target.value)} /></div></div>
            <Label htmlFor="prompt-workflow">Workflow</Label><Input id="prompt-workflow" required value={workflow} onChange={event => setWorkflow(event.target.value)} />
            <Label htmlFor="prompt-description">Description</Label><Textarea id="prompt-description" value={description} onChange={event => setDescription(event.target.value)} />
            <Label htmlFor="prompt-body">Body</Label><Textarea id="prompt-body" required className="min-h-40 font-mono text-xs" value={body} onChange={event => setBody(event.target.value)} />
            <Label htmlFor="prompt-variables">Variables (comma separated)</Label><Input id="prompt-variables" value={variables} onChange={event => setVariables(event.target.value)} placeholder="company, market" />
            <Failure error={create.error} /><Button type="submit" disabled={create.isPending}>{create.isPending ? 'Creating...' : 'Create template'}</Button>
          </form>
        </Panel>
      </div>
      {currentId && <TemplateEditor key={currentId} id={currentId} scope={scope} />}
    </div>
  </>;
}

function TemplateEditor({ id, scope }: { id: string; scope: string }) {
  const client = useQueryClient();
  const detailKey = keyFor(scope, 'detail', id);
  const detail = useQuery({ queryKey: detailKey, queryFn: () => promptsApi.detail(id), retry: false });
  const update = (next: TemplateDetail) => { client.setQueryData(detailKey, next); void client.invalidateQueries({ queryKey: keyFor(scope, 'list') }); };
  return detail.isPending ? <LoadingState message="Loading template..." /> : detail.error ? <ErrorState message={`Could not load template: ${message(detail.error)}`} onRetry={() => void detail.refetch()} /> : <VersionWorkspace key={`${id}:${detail.data.versions[0]?.version ?? 0}`} detail={detail.data} update={update} />;
}

function VersionWorkspace({ detail, update }: { detail: TemplateDetail; update: (next: TemplateDetail) => void }) {
  const [body, setBody] = useState(detail.versions[0]?.body ?? '');
  const [variables, setVariables] = useState((detail.versions[0]?.variables ?? []).join(', '));
  const [version, setVersion] = useState(detail.active_version ?? detail.versions[0]?.version ?? 1);
  const [values, setValues] = useState('{}');
  const [validationError, setValidationError] = useState<string | null>(null);
  const createVersion = useMutation({ mutationFn: (content: PromptContent) => promptsApi.createVersion(detail.id, content), onSuccess: update });
  const activate = useMutation({ mutationFn: (selected: number) => promptsApi.activate(detail.id, selected), onSuccess: update });
  const preview = useMutation({ mutationFn: (request: { version: number; values: Record<string, string> }) => promptsApi.preview(detail.id, request) });
  return <div className="min-w-0 space-y-6">
    <Panel title={detail.name}><p className="break-words text-sm text-muted-foreground">{detail.description || 'No description'}</p><p className="break-all text-xs">{detail.key} · {detail.workflow} · Active: {detail.active_version == null ? 'None' : `v${detail.active_version}`}</p></Panel>
    <Panel title="Versions"><div className="space-y-3">{detail.versions.map(item => <div key={item.id} className="rounded-md border p-3 text-sm"><div className="flex flex-wrap items-center justify-between gap-2"><strong>v{item.version}{item.version === detail.active_version ? ' · Active' : ''}</strong><Button size="sm" variant="outline" disabled={activate.isPending || item.version === detail.active_version} onClick={() => activate.mutate(item.version)}>{item.version === detail.active_version ? 'Active version' : item.version < (detail.active_version ?? 0) ? 'Rollback to this version' : 'Activate version'}</Button></div><p className="mt-2 break-all font-mono text-xs text-muted-foreground">Checksum {item.checksum} · Created {new Date(item.created_at).toLocaleString()} by {item.created_by}</p><p className="mt-1 text-xs text-muted-foreground">Variables: {item.variables.join(', ') || 'None'}</p><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words bg-muted p-2 text-xs">{item.body}</pre></div>)}</div><Failure error={activate.error} /></Panel>
    <Panel title="New immutable version"><form className="space-y-3" onSubmit={event => { event.preventDefault(); createVersion.mutate({ body, variables: variablesFrom(variables) }); }}><Label htmlFor="version-body">Body</Label><Textarea id="version-body" required className="min-h-40 font-mono text-xs" value={body} onChange={event => setBody(event.target.value)} /><Label htmlFor="version-variables">Variables (comma separated)</Label><Input id="version-variables" value={variables} onChange={event => setVariables(event.target.value)} /><Failure error={createVersion.error} /><Button type="submit" disabled={createVersion.isPending}>{createVersion.isPending ? 'Saving...' : 'Create version'}</Button></form></Panel>
    <Panel title="Preview rendered template"><form className="space-y-3" onSubmit={event => { event.preventDefault(); setValidationError(null); preview.reset(); try { const parsed: unknown = JSON.parse(values); if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || Object.values(parsed).some(value => typeof value !== 'string')) throw new Error('Values must be a JSON object of strings.'); preview.mutate({ version, values: parsed as Record<string, string> }); } catch (error) { setValidationError(message(error)); } }}><Label htmlFor="preview-version">Version</Label><select id="preview-version" className={selectClass} value={version} onChange={event => { setVersion(Number(event.target.value)); preview.reset(); }}>{detail.versions.map(item => <option key={item.id} value={item.version}>v{item.version}</option>)}</select><Label htmlFor="preview-values">Values (JSON object of strings)</Label><Textarea id="preview-values" className="min-h-24 font-mono text-xs" value={values} onChange={event => setValues(event.target.value)} /><Failure error={validationError || preview.error} /><Button type="submit" disabled={preview.isPending}>{preview.isPending ? 'Rendering...' : 'Preview'}</Button></form>{preview.data && <div><p className="text-xs font-medium">Rendered v{preview.data.version}</p><pre className="mt-2 whitespace-pre-wrap break-words bg-muted p-3 text-xs">{preview.data.rendered}</pre></div>}</Panel>
    <Panel title="History">{detail.history.length ? <ol className="space-y-2">{detail.history.map(item => <li key={item.id} className="border-b pb-2 text-sm"><strong>{item.action}</strong> · v{item.version}<p className="text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()} · {item.actor_id}</p></li>)}</ol> : <EmptyState title="No history yet" />}</Panel>
  </div>;
}
