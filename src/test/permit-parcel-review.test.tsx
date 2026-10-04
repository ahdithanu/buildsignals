import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { parcelReferencesApi } from '@/api/parcelReferences';
import { PermitParcelReview } from '@/components/PermitParcelReview';
import { ApiError } from '@/api/client';

const auth = vi.hoisted(() => ({ organizationId: 'org-a', isAuthenticated: true, role: 'editor' }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/parcelReferences', () => ({ parcelReferencesApi: { sources: vi.fn(), candidates: vi.fn(), accept: vi.fn() } }));
const candidate = {
  permit_raw_source_record_id: 'permit-raw', status: 'candidate_requires_review', truncated: false,
  candidates: [{ parcel_id: 'parcel', external_parcel_id: '001', raw_source_record_id: 'parcel-raw',
    identity_assessment: 'address_corroborated', state_comparison: 'match', city_comparison: 'match', street_comparison: 'match',
    captured_at: '2026-09-19T12:00:00Z', last_verified_at: '2026-09-19T12:00:00Z', has_valid_coordinates: true }],
};
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><PermitParcelReview permitId="permit" /></MemoryRouter></QueryClientProvider>);
}
async function selectSource() {
  await screen.findByRole('option', { name: 'Assessor' });
  fireEvent.change(screen.getByLabelText('Parcel source'), { target: { value: 'source' } });
  await screen.findByRole('link', { name: '001' });
}
beforeEach(() => {
  vi.resetAllMocks(); auth.role = 'editor';
  vi.mocked(parcelReferencesApi.sources).mockResolvedValue([{ id: 'source', name: 'Assessor', record_type: 'parcel', is_active: true }]);
  vi.mocked(parcelReferencesApi.candidates).mockResolvedValue(candidate);
  vi.mocked(parcelReferencesApi.accept).mockResolvedValue({ id: 'relationship' });
});
it('requires explicit review inputs and submits both evidence versions', async () => {
  setup(); await selectSource();
  expect(screen.getByRole('button', { name: 'Accept parcel identity' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Review rationale'), { target: { value: 'Reviewed both original source records.' } });
  fireEvent.change(screen.getByLabelText(/Analyst confidence/), { target: { value: '0.9' } });
  fireEvent.click(screen.getByRole('button', { name: 'Accept parcel identity' }));
  await waitFor(() => expect(parcelReferencesApi.accept).toHaveBeenCalledWith('permit', {
    parcel_source_id: 'source', parcel_id: 'parcel', expected_permit_raw_id: 'permit-raw',
    expected_parcel_raw_id: 'parcel-raw', reason: 'Reviewed both original source records.', confidence: 0.9,
  }));
  expect(await screen.findByText(/Parcel identity accepted/)).toBeInTheDocument();
});
it('does not expose acceptance to viewers', async () => {
  auth.role = 'viewer'; setup(); await selectSource();
  expect(screen.queryByRole('button', { name: 'Accept parcel identity' })).not.toBeInTheDocument();
});
it('does not offer acceptance for ambiguous matches', async () => {
  vi.mocked(parcelReferencesApi.candidates).mockResolvedValue({ ...candidate, status: 'ambiguous' });
  setup(); await selectSource();
  expect(screen.queryByRole('button', { name: 'Accept parcel identity' })).not.toBeInTheDocument();
});
it('distinguishes missing active sources', async () => {
  vi.mocked(parcelReferencesApi.sources).mockResolvedValue([]);
  setup(); expect(await screen.findByText('No active parcel sources.')).toBeInTheDocument();
  expect(parcelReferencesApi.candidates).not.toHaveBeenCalled();
});
it('requires new review inputs after a stale-evidence rejection', async () => {
  vi.mocked(parcelReferencesApi.accept).mockRejectedValue(new ApiError('stale', 409));
  setup(); await selectSource();
  fireEvent.change(screen.getByLabelText('Review rationale'), { target: { value: 'Reviewed both original source records.' } });
  fireEvent.change(screen.getByLabelText(/Analyst confidence/), { target: { value: '0.9' } });
  fireEvent.click(screen.getByRole('button', { name: 'Accept parcel identity' }));
  await screen.findByText('Evidence changed or the match needs further review.');
  expect(screen.getByRole('button', { name: 'Accept parcel identity' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Reload evidence' }));
  expect(screen.getByLabelText('Review rationale')).toHaveValue('');
  expect(screen.getByRole('button', { name: 'Accept parcel identity' })).toBeDisabled();
});
