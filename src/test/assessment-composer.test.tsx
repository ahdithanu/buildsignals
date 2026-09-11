import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createHash, webcrypto } from 'node:crypto';
import { AssessmentComposer } from '@/components/AssessmentComposer';
import { assessmentsApi, type AssessmentRevision } from '@/api/assessments';
import { graphApi } from '@/api/graph';
import type { GraphEntityDetail, GraphEntitySearchResult } from '@/types/graph';

vi.mock('@/api/assessments', () => ({ assessmentsApi: { save: vi.fn() } }));
vi.mock('@/api/graph', () => ({ graphApi: { searchEntities: vi.fn(), entityDetail: vi.fn() } }));
const auth = vi.hoisted(() => ({ organizationId: 'org' as string | null, user: { id: 'author' }, role: 'editor' }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
const onSaved = vi.fn();
const onCancel = vi.fn();
const parcel = { id: 'parcel', display_name: 'Parcel A', entity_type: 'parcel' } as GraphEntitySearchResult;
const owner = { id: 'owner', display_name: 'Owner B', entity_type: 'owner' } as GraphEntitySearchResult;
function detail(id = 'parcel', evidenceId = 'e1', excerpt = 'Application received'): GraphEntityDetail {
  const timestamp = '2026-09-10T12:00:00.123456Z';
  return { id, related: [{ entity: { id: id === 'owner' ? 'parcel' : 'owner' }, direction: id === 'owner' ? 'incoming' : 'outgoing', relationship: {
    id: `relationship-${evidenceId}`, is_current: true, updated_at: timestamp, last_verified_at: timestamp,
    evidence: [{ id: evidenceId, source_system: 'Planning', excerpt, confidence: 1, created_at: timestamp }],
  } }] } as GraphEntityDetail;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const view = (signalId: string) => <QueryClientProvider client={client}><AssessmentComposer signalId={signalId} onSaved={onSaved} onCancel={onCancel} /></QueryClientProvider>;
  const rendered = render(view('signal'));
  return { ...rendered, client, changeContext: (signalId = 'signal') => rendered.rerender(view(signalId)) };
}
function fill(label: string, value: string) { fireEvent.change(screen.getByLabelText(label), { target: { value } }); }
function submit() { fireEvent.submit(screen.getByRole('form', { name: 'New assessment' })); }
function entry(name: string) { return within(screen.getByRole('group', { name: `Implication for ${name}` })); }
async function searchEntity(query: string, id: string) {
  fill('Find affected entity', query);
  fireEvent.click(screen.getByRole('button', { name: 'Search entities' }));
  await waitFor(() => expect(screen.getByLabelText('Affected entity')).not.toBeDisabled());
  fill('Affected entity', id);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Add citation' })).toBeEnabled());
}
function completeFields(name = 'Parcel A') {
  fireEvent.change(entry(name).getByLabelText('Investment mechanism'), { target: { value: ' Potential additional units ' } });
  fireEvent.change(entry(name).getByLabelText('Time horizon'), { target: { value: ' 12 months ' } });
}
async function complete() {
  const rendered = show();
  fill('Detected change', ' Filing submitted ');
  fill('Investment hypothesis', ' Possible density uplift ');
  fill('Change confidence rationale', ' Official source ');
  fill('Thesis confidence rationale', ' Entitlement uncertain ');
  fill('Investigation questions', ' Check utilities\nReview zoning ');
  await searchEntity('Parcel', 'parcel');
  completeFields();
  fireEvent.click(screen.getByRole('button', { name: 'Add citation' }));
  fill('Citation rationale 1', ' Filing establishes the change ');
  fireEvent.click(entry('Parcel A').getByRole('checkbox', { name: 'Planning · e1' }));
  return rendered;
}

describe('Assessment authoring', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.stubGlobal('crypto', webcrypto);
    auth.organizationId = 'org';
    auth.user = { id: 'author' };
    auth.role = 'editor';
    vi.mocked(graphApi.searchEntities).mockResolvedValue([parcel]);
    vi.mocked(graphApi.entityDetail).mockResolvedValue(detail());
    vi.mocked(assessmentsApi.save).mockResolvedValue({ id: 'revision' } as AssessmentRevision);
  });
  afterEach(() => vi.unstubAllGlobals());
  it('saves canonical IDs, explicit associations, trimmed fields and an unknown event date', async () => {
    await complete(); submit();
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('revision'));
    expect(graphApi.entityDetail).toHaveBeenCalledTimes(2);
    expect(assessmentsApi.save).toHaveBeenCalledWith('signal', expect.objectContaining({
      detected_change: 'Filing submitted', event_at: null,
      change_confidence: { level: 'unassessed', rationale: 'Official source' },
      citations: [{ evidence_id: 'e1', claim: 'change', stance: 'supports', rationale: 'Filing establishes the change' }],
      implications: [{ entity_id: 'parcel', mechanism: 'Potential additional units', horizon: '12 months', direction: 'uncertain', evidence_ids: ['e1'] }],
      further_investigation: ['Check utilities', 'Review zoning'],
      source_precondition: { schema_version: '1', evidence: [{
        evidence_id: 'e1', relationship_id: 'relationship-e1',
        content_sha256: createHash('sha256').update(JSON.stringify(['Planning', null, null, null, 'Application received'])).digest('hex'),
        observed_at: null, created_at: '2026-09-10T12:00:00.123456Z', confidence: 1,
        source_entity_id: 'parcel', target_entity_id: 'owner',
        relationship_updated_at: '2026-09-10T12:00:00.123456Z',
        relationship_last_verified_at: '2026-09-10T12:00:00.123456Z', relationship_is_current: true,
      }] },
    }));
  });
  it('saves a supplied event timestamp with explicit UTC semantics and no inferred date', async () => {
    await complete(); fill('Event date and time (UTC, optional)', '2026-09-10T14:05'); submit();
    await waitFor(() => expect(assessmentsApi.save).toHaveBeenCalled());
    expect(assessmentsApi.save).toHaveBeenCalledWith('signal', expect.objectContaining({ event_at: '2026-09-10T14:05:00.000Z' }));
  });
  it('rejects invalid non-minute date input instead of rounding it', async () => {
    await complete(); fill('Event date and time (UTC, optional)', '2026-09-10T14:05:30'); submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('valid event date');
    expect(assessmentsApi.save).not.toHaveBeenCalled();
  });
  it('retains previous entries and citations when searching for a second entity', async () => {
    await complete();
    vi.mocked(graphApi.searchEntities).mockResolvedValue([owner]);
    vi.mocked(graphApi.entityDetail).mockImplementation(async id => id === 'owner' ? detail('owner', 'e2', 'Ownership filing') : detail());
    await searchEntity('Owner', 'owner'); completeFields('Owner B');
    fireEvent.click(screen.getByRole('button', { name: 'Add citation' }));
    fill('Source 2', 'e2'); fill('Citation rationale 2', 'Owner named in filing');
    expect(entry('Parcel A').getByLabelText('Investment mechanism')).toHaveValue(' Potential additional units ');
    expect(screen.getByLabelText('Citation rationale 1')).toHaveValue(' Filing establishes the change ');
    expect(entry('Parcel A').queryByRole('checkbox', { name: 'Planning · e2' })).not.toBeInTheDocument();
    expect(entry('Owner B').queryByRole('checkbox', { name: 'Planning · e1' })).not.toBeInTheDocument();
    submit();
    expect(screen.getByRole('alert')).toHaveTextContent('each affected entity');
    fireEvent.click(entry('Owner B').getByRole('checkbox', { name: 'Planning · e2' }));
    submit();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(vi.mocked(assessmentsApi.save).mock.calls[0][1].implications).toEqual([
      { entity_id: 'parcel', mechanism: 'Potential additional units', horizon: '12 months', direction: 'uncertain', evidence_ids: ['e1'] },
      { entity_id: 'owner', mechanism: 'Potential additional units', horizon: '12 months', direction: 'uncertain', evidence_ids: ['e2'] },
    ]);
  });
  it('shares one citation across related entities without duplicating it, and preserves it when one entity is removed', async () => {
    await complete();
    vi.mocked(graphApi.searchEntities).mockResolvedValue([owner]);
    vi.mocked(graphApi.entityDetail).mockImplementation(async id => detail(id));
    await searchEntity('Owner', 'owner'); completeFields('Owner B');
    fireEvent.click(entry('Owner B').getByRole('checkbox', { name: 'Planning · e1' }));
    expect(screen.getByText('Citations (1/100)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove Parcel A' }));
    expect(screen.getByLabelText('Citation rationale 1')).toHaveValue(' Filing establishes the change ');
    submit();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const draft = vi.mocked(assessmentsApi.save).mock.calls[0][1];
    expect(draft.citations).toHaveLength(1);
    expect(draft.source_precondition?.evidence).toHaveLength(1);
    expect(draft.implications).toEqual([expect.objectContaining({ entity_id: 'owner', evidence_ids: ['e1'] })]);
  });
  it('removes orphaned citations when their last entity is removed', async () => {
    await complete(); fireEvent.click(screen.getByRole('button', { name: 'Remove Parcel A' }));
    expect(screen.queryByLabelText('Citation rationale 1')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
    expect(screen.getByLabelText('Detected change')).toHaveValue(' Filing submitted ');
  });
  it('requires supporting evidence and disallows duplicate claim stances', async () => {
    await complete(); fill('Stance 1', 'contradicts'); submit();
    expect(screen.getByRole('alert')).toHaveTextContent('requires supporting evidence');
    fill('Stance 1', 'supports'); fireEvent.click(screen.getByRole('button', { name: 'Add citation' }));
    fill('Citation rationale 2', 'Other interpretation'); submit();
    expect(screen.getByRole('alert')).toHaveTextContent('one stance per source and claim');
    expect(assessmentsApi.save).not.toHaveBeenCalled();
    fill('Claim 2', 'thesis'); fill('Stance 2', 'contradicts'); submit();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
  it('clears an implication association only after its last citation is removed', async () => {
    await complete(); fireEvent.click(screen.getByRole('button', { name: 'Add citation' }));
    fill('Claim 2', 'thesis'); fill('Citation rationale 2', 'Thesis context');
    fireEvent.click(screen.getByRole('button', { name: 'Remove citation 1' }));
    expect(entry('Parcel A').getByRole('checkbox', { name: 'Planning · e1' })).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Remove citation 1' }));
    expect(entry('Parcel A').queryByRole('checkbox')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add citation' }));
    expect(entry('Parcel A').getByRole('checkbox', { name: 'Planning · e1' })).not.toBeChecked();
  });
  it('requires reassociation after a citation source changes', async () => {
    const twoSources = detail(); twoSources.related[0].relationship.evidence.push({ ...twoSources.related[0].relationship.evidence[0], id: 'e2' });
    vi.mocked(graphApi.entityDetail).mockResolvedValue(twoSources);
    await complete(); fill('Source 1', 'e2');
    expect(screen.getByLabelText('Citation rationale 1')).toHaveValue('');
    expect(entry('Parcel A').getByRole('checkbox', { name: 'Planning · e2' })).not.toBeChecked();
    expect(entry('Parcel A').queryByRole('checkbox', { name: 'Planning · e1' })).not.toBeInTheDocument();
    fill('Citation rationale 1', 'Rationale for the replacement source');
    submit(); expect(screen.getByRole('alert')).toHaveTextContent('each affected entity');
    expect(assessmentsApi.save).not.toHaveBeenCalled();
  });
  it('preserves and retries a draft after an API failure', async () => {
    vi.mocked(assessmentsApi.save).mockRejectedValueOnce(new Error('Save unavailable'));
    await complete(); submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Save unavailable');
    expect(screen.getByLabelText('Detected change')).toHaveValue(' Filing submitted ');
    expect(entry('Parcel A').getByRole('checkbox')).toBeChecked();
    expect(onSaved).not.toHaveBeenCalled();
    submit(); await waitFor(() => expect(onSaved).toHaveBeenCalledWith('revision'));
  });
  it('blocks a stale evidence snapshot until the author reviews refreshed evidence', async () => {
    await complete();
    vi.mocked(graphApi.entityDetail).mockResolvedValue(detail('parcel', 'e1', 'Application withdrawn'));
    submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Source evidence changed');
    expect(screen.getByText('Application withdrawn')).toBeInTheDocument();
    expect(assessmentsApi.save).not.toHaveBeenCalled();
    fill('Citation rationale 1', 'Updated interpretation'); submit();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
  it('rejects evidence removed during the final reference refresh', async () => {
    await complete(); vi.mocked(graphApi.entityDetail).mockResolvedValue({ id: 'parcel', related: [] } as unknown as GraphEntityDetail);
    submit();
    await waitFor(() => expect(screen.getAllByRole('alert').some(node => node.textContent?.includes('Source evidence changed'))).toBe(true));
    expect(assessmentsApi.save).not.toHaveBeenCalled(); submit();
    expect(assessmentsApi.save).not.toHaveBeenCalled();
  });
  it('does not fall back to an unprotected save when source-version metadata is incomplete', async () => {
    const incomplete = detail(); delete incomplete.related[0].relationship.updated_at;
    vi.mocked(graphApi.entityDetail).mockResolvedValue(incomplete);
    await complete(); submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Source version metadata is unavailable');
    expect(assessmentsApi.save).not.toHaveBeenCalled();
  });
  it('fails closed when secure hashing is unavailable', async () => {
    await complete(); vi.stubGlobal('crypto', {}); submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Secure source verification is unavailable');
    expect(assessmentsApi.save).not.toHaveBeenCalled();
  });
  it('fails closed on a refresh error and allows retry without discarding fields', async () => {
    await complete(); vi.mocked(graphApi.entityDetail).mockRejectedValueOnce(new Error('Evidence unavailable'));
    submit();
    await screen.findByRole('button', { name: 'Retry source evidence for Parcel A' });
    expect(assessmentsApi.save).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Retry source evidence for Parcel A' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled());
    expect(screen.getByLabelText('Citation rationale 1')).toHaveValue(' Filing establishes the change ');
    submit(); await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
  it('supports search error retry and empty results without losing an existing entry', async () => {
    await complete(); vi.mocked(graphApi.searchEntities).mockRejectedValueOnce(new Error('Search unavailable'));
    fill('Find affected entity', 'Owner'); fireEvent.click(screen.getByRole('button', { name: 'Search entities' }));
    await screen.findByRole('button', { name: 'Retry entity search' });
    expect(entry('Parcel A').getByLabelText('Time horizon')).toHaveValue(' 12 months ');
    vi.mocked(graphApi.searchEntities).mockResolvedValue([]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry entity search' }));
    await screen.findByText('No matching entities.');
    expect(screen.getByLabelText('Citation rationale 1')).toHaveValue(' Filing establishes the change ');
  });
  it('does not duplicate selected entities and bounds entity additions at 50', async () => {
    const rows = Array.from({ length: 51 }, (_, index) => ({ ...parcel, id: `p${index}`, display_name: `Parcel ${index}` }));
    vi.mocked(graphApi.searchEntities).mockResolvedValue(rows);
    vi.mocked(graphApi.entityDetail).mockImplementation(async id => detail(id));
    show(); await searchEntity('Parcel', 'p0'); fill('Affected entity', 'p0');
    expect(screen.getByText('Affected entities (1/50)')).toBeInTheDocument();
    for (let index = 1; index < 50; index++) fill('Affected entity', `p${index}`);
    expect(screen.getByText('Affected entities (50/50)')).toBeInTheDocument();
    expect(screen.getByLabelText('Affected entity')).toBeDisabled();
    fill('Affected entity', 'p50');
    expect(screen.queryByRole('group', { name: 'Implication for Parcel 50' })).not.toBeInTheDocument();
  });
  it('bounds citations at 100', async () => {
    await complete();
    const addCitation = screen.getByRole('button', { name: 'Add citation' });
    for (let index = 1; index < 100; index++) fireEvent.click(addCitation);
    expect(screen.getByText('Citations (100/100)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add citation' })).toBeDisabled();
  }, 20000);
  it('bounds source associations to 50 per implication', async () => {
    const sources = detail();
    sources.related[0].relationship.evidence = Array.from({ length: 51 }, (_, index) => ({
      ...sources.related[0].relationship.evidence[0], id: `e${index + 1}`,
    }));
    vi.mocked(graphApi.entityDetail).mockResolvedValue(sources);
    await complete();
    const addCitation = screen.getByRole('button', { name: 'Add citation' });
    const implication = entry('Parcel A');
    for (let index = 2; index <= 51; index++) {
      fireEvent.click(addCitation);
      fill(`Source ${index}`, `e${index}`);
      if (index <= 50) fireEvent.click(implication.getByRole('checkbox', { name: `Planning · e${index}` }));
    }
    expect(entry('Parcel A').getByText('Implication evidence (50/50)')).toBeInTheDocument();
    expect(entry('Parcel A').getByRole('checkbox', { name: 'Planning · e51' })).toBeDisabled();
    fireEvent.click(entry('Parcel A').getByRole('checkbox', { name: 'Planning · e1' }));
    expect(entry('Parcel A').getByRole('checkbox', { name: 'Planning · e51' })).toBeEnabled();
  }, 20000);
  it('does not attribute a mismatched detail response to the selected entity', async () => {
    vi.mocked(graphApi.entityDetail).mockResolvedValue(detail('other-entity'));
    show(); fill('Find affected entity', 'Parcel');
    fireEvent.click(screen.getByRole('button', { name: 'Search entities' }));
    await screen.findByLabelText('Affected entity'); fill('Affected entity', 'parcel');
    await screen.findByRole('button', { name: 'Retry source evidence for Parcel A' });
    expect(screen.getByRole('button', { name: 'Add citation' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  });
  it('validates investigation question limits', async () => {
    await complete(); fill('Investigation questions', Array.from({ length: 31 }, () => 'Question').join('\n')); submit();
    expect(screen.getByRole('alert')).toHaveTextContent('1 to 30 investigation questions');
    expect(assessmentsApi.save).not.toHaveBeenCalled();
  });
  it('prevents double submission while checking evidence and saving', async () => {
    await complete(); const pending = deferred<GraphEntityDetail>();
    vi.mocked(graphApi.entityDetail).mockReturnValue(pending.promise);
    submit(); submit();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Cancel assessment' })).toBeDisabled();
    await act(async () => pending.resolve(detail()));
    await waitFor(() => expect(assessmentsApi.save).toHaveBeenCalledTimes(1));
  });
  it('does not save after changing the signal while evidence is revalidating', async () => {
    const rendered = await complete(); const pending = deferred<GraphEntityDetail>();
    vi.mocked(graphApi.entityDetail).mockReturnValue(pending.promise);
    submit(); await waitFor(() => expect(graphApi.entityDetail).toHaveBeenCalledTimes(2));
    rendered.changeContext('next-signal');
    expect(screen.getByLabelText('Detected change')).toHaveValue('');
    await act(async () => pending.resolve(detail()));
    expect(assessmentsApi.save).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });
  it('ignores late save callbacks after an organization change and resets the draft', async () => {
    const pending = deferred<AssessmentRevision>(); vi.mocked(assessmentsApi.save).mockReturnValue(pending.promise);
    const rendered = await complete(); submit();
    await waitFor(() => expect(assessmentsApi.save).toHaveBeenCalled());
    auth.organizationId = 'other'; rendered.changeContext();
    expect(screen.getByLabelText('Detected change')).toHaveValue('');
    expect(screen.getByText('Affected entities (0/50)')).toBeInTheDocument();
    await act(async () => pending.resolve({ id: 'old-revision' } as AssessmentRevision));
    expect(onSaved).not.toHaveBeenCalled();
  });
  it('clears an author draft when the account changes within the same organization', async () => {
    const rendered = await complete();
    auth.user = { id: 'another-author' }; rendered.changeContext();
    expect(screen.getByLabelText('Detected change')).toHaveValue('');
    expect(screen.getByText('Affected entities (0/50)')).toBeInTheDocument();
  });
  it('keeps network actions disabled without an organization', () => {
    auth.organizationId = null; show(); fill('Find affected entity', 'Parcel');
    expect(screen.getByRole('button', { name: 'Search entities' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
    expect(graphApi.searchEntities).not.toHaveBeenCalled();
  });
});
