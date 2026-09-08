import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AssessmentComposer } from '@/components/AssessmentComposer';
import { assessmentsApi, type AssessmentRevision } from '@/api/assessments';
import { graphApi } from '@/api/graph';
import type { GraphEntityDetail, GraphEntitySearchResult } from '@/types/graph';

vi.mock('@/api/assessments', () => ({ assessmentsApi: { save: vi.fn() } }));
vi.mock('@/api/graph', () => ({ graphApi: { searchEntities: vi.fn(), entityDetail: vi.fn() } }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org' }) }));
const onSaved = vi.fn();
const onCancel = vi.fn();
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><AssessmentComposer signalId="signal" onSaved={onSaved} onCancel={onCancel} /></QueryClientProvider>);
}
function fill(label: string, value: string) { fireEvent.change(screen.getByLabelText(label), { target: { value } }); }
async function complete() {
  show();
  fill('Detected change', ' Filing submitted ');
  fill('Investment hypothesis', ' Possible density uplift ');
  fill('Change confidence rationale', ' Official source ');
  fill('Thesis confidence rationale', ' Entitlement uncertain ');
  fill('Investment mechanism', ' Potential additional units ');
  fill('Time horizon', ' 12 months ');
  fill('Investigation questions', ' Check utilities\nReview zoning ');
  fill('Find affected entity', 'Parcel');
  fireEvent.click(screen.getByRole('button', { name: 'Search entities' }));
  await screen.findByLabelText('Affected entity');
  fill('Affected entity', 'parcel');
  fireEvent.click(await screen.findByRole('button', { name: 'Add citation' }));
  fill('Citation rationale 1', ' Filing establishes the change ');
}
describe('Assessment authoring', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(graphApi.searchEntities).mockResolvedValue([{ id: 'parcel', display_name: 'Parcel A', entity_type: 'parcel' } as GraphEntitySearchResult]);
    vi.mocked(graphApi.entityDetail).mockResolvedValue({ id: 'parcel', related: [{ relationship: { evidence: [{ id: 'e1', source_system: 'Planning', excerpt: 'Application received' }] } }] } as GraphEntityDetail);
    vi.mocked(assessmentsApi.save).mockResolvedValue({ id: 'revision' } as AssessmentRevision);
  });
  it('saves canonical reference IDs, trimmed content and unassessed confidence', async () => {
    await complete(); fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('revision'));
    expect(assessmentsApi.save).toHaveBeenCalledWith('signal', expect.objectContaining({
      detected_change: 'Filing submitted',
      change_confidence: { level: 'unassessed', rationale: 'Official source' },
      citations: [{ evidence_id: 'e1', claim: 'change', stance: 'supports', rationale: 'Filing establishes the change' }],
      implications: [{ entity_id: 'parcel', mechanism: 'Potential additional units', horizon: '12 months', direction: 'uncertain', evidence_ids: ['e1'] }],
      further_investigation: ['Check utilities', 'Review zoning'],
    }));
  });
  it('requires supporting evidence and disallows duplicate claim stances', async () => {
    await complete(); fill('Stance 1', 'contradicts');
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('requires supporting evidence');
    fill('Stance 1', 'supports'); fireEvent.click(screen.getByRole('button', { name: 'Add citation' }));
    fill('Citation rationale 2', 'Other interpretation');
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('one stance per source and claim');
    expect(assessmentsApi.save).not.toHaveBeenCalled();
    fill('Claim 2', 'thesis'); fill('Stance 2', 'contradicts');
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
  it('preserves the draft after an API failure', async () => {
    vi.mocked(assessmentsApi.save).mockRejectedValue(new Error('Save unavailable'));
    await complete(); fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Save unavailable');
    expect(screen.getByLabelText('Detected change')).toHaveValue(' Filing submitted ');
    expect(onSaved).not.toHaveBeenCalled();
  });
  it('clears citations when the affected entity changes', async () => {
    await complete(); fill('Affected entity', '');
    expect(screen.queryByLabelText('Citation rationale 1')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  });
});
