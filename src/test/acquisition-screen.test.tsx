import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { AcquisitionScreenPanel } from '@/components/AcquisitionScreenPanel';
import { apiClient } from '@/api/client';

const auth = vi.hoisted(() => ({ role: 'admin' }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'o', user: { id: 'u' }, role: auth.role }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), download: vi.fn() } }));
vi.mock('@/components/SavedAcquisitionCriteria', () => ({
  SavedAcquisitionCriteria: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <label>Saved buy box
      <select aria-label="Saved buy box" value={value} onChange={event => onChange(event.target.value)}>
        <option value="">Default criteria</option>
        <option value="box-1">Box 1</option>
      </select>
    </label>
  ),
}));
afterEach(() => { vi.restoreAllMocks(); auth.role = 'admin'; window.localStorage.clear(); });
it('shows unknown diligence explicitly rather than a fabricated fit score', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ status: 'needs_diligence', counts: { pass: 1, fail: 0, unknown: 1 }, criteria: [
    { key: 'occupancy', label: 'Occupancy', target: '80-100%', status: 'unknown', value: null, reason: 'Rent roll required' },
  ] });
  render(<QueryClientProvider client={new QueryClient()}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  expect(await screen.findByText(/1 pass, 0 fail, 1 unknown/)).toBeInTheDocument();
  expect(screen.getByText(/Not established/)).toHaveTextContent('Rent roll required');
});

it('shows reviewed observations without presenting them as verified fits', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ status: 'needs_diligence', counts: { pass: 0, fail: 0, unknown: 1 }, criteria: [
    { key: 'occupancy', label: 'Occupancy', target: '80-100%', status: 'unknown', value: null, reason: 'Rent roll required',
      reviewed_observations: [{ assessment: 'supports', changes_screening_result: false, independently_verified: false,
        observation: { metric: 'leased_area_occupancy_percent', value: 82, as_of: '2026-09-01', scope: 'partial', methodology: 'Measured from supplied rent roll excerpt.' } }] },
  ] });
  render(<QueryClientProvider client={new QueryClient()}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  expect(await screen.findByText(/82 leased area occupancy percent/)).toBeInTheDocument();
  expect(screen.getByText(/does not change status/)).toBeInTheDocument();
  expect(screen.getByText(/0 pass, 0 fail, 1 unknown/)).toBeInTheDocument();
});

it('downloads the applied profile and market using the authenticated client', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ status: 'needs_diligence', counts: { pass: 0, fail: 0, unknown: 1 }, criteria: [] });
  vi.mocked(apiClient.download).mockResolvedValue({ blob: new Blob(['{}']), filename: null, exportedCount: null, omittedCount: null });
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:test') });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  render(<QueryClientProvider client={new QueryClient()}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  await screen.findByText(/Diligence required/);
  fireEvent.change(screen.getByLabelText('Profile'), { target: { value: 'small_bay_retail' } });
  fireEvent.change(screen.getByLabelText('Target city'), { target: { value: 'Columbus' } });
  fireEvent.change(screen.getByLabelText('State'), { target: { value: 'OH' } });
  fireEvent.click(screen.getByText('Apply'));
  await waitFor(() => expect(screen.getByLabelText('Download acquisition screen')).not.toBeDisabled());
  fireEvent.click(screen.getByLabelText('Download acquisition screen'));
  await waitFor(() => expect(click).toHaveBeenCalled());
  expect(apiClient.download).toHaveBeenCalledWith('/deals/d/acquisition-screen/export?profile=small_bay_retail&market_city=Columbus&market_state=OH', 'POST');
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test');
});

it('persists profile and target market per authenticated deal workspace', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ status: 'needs_diligence', counts: { pass: 0, fail: 0, unknown: 1 }, criteria: [] });
  const query = new QueryClient();
  const view = render(<QueryClientProvider client={query}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  await screen.findByText(/Diligence required/);
  fireEvent.change(screen.getByLabelText('Profile'), { target: { value: 'small_bay_retail' } });
  fireEvent.change(screen.getByLabelText('Target city'), { target: { value: 'Columbus' } });
  fireEvent.change(screen.getByLabelText('State'), { target: { value: 'OH' } });
  fireEvent.click(screen.getByText('Apply'));
  await waitFor(() => expect(apiClient.get).toHaveBeenLastCalledWith('/deals/d/acquisition-screen', { profile: 'small_bay_retail', market_city: 'Columbus', market_state: 'OH' }));

  view.unmount();
  render(<QueryClientProvider client={new QueryClient()}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  expect(screen.getByLabelText('Profile')).toHaveValue('small_bay_retail');
  expect(screen.getByLabelText('Target city')).toHaveValue('Columbus');
  expect(screen.getByLabelText('State')).toHaveValue('OH');
  await waitFor(() => expect(apiClient.get).toHaveBeenLastCalledWith('/deals/d/acquisition-screen', { profile: 'small_bay_retail', market_city: 'Columbus', market_state: 'OH' }));

  render(<QueryClientProvider client={new QueryClient()}><AcquisitionScreenPanel dealId="other" /></QueryClientProvider>);
  const profileFields = screen.getAllByLabelText('Profile');
  expect(profileFields[profileFields.length - 1]).toHaveValue('small_multifamily');
});

it('persists selected saved buy box per authenticated deal workspace', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ status: 'needs_diligence', counts: { pass: 0, fail: 0, unknown: 1 }, criteria: [] });
  const view = render(<QueryClientProvider client={new QueryClient()}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  await screen.findByText(/Diligence required/);
  fireEvent.change(screen.getByLabelText('Saved buy box'), { target: { value: 'box-1' } });
  await waitFor(() => expect(apiClient.get).toHaveBeenLastCalledWith('/deals/d/acquisition-screen', { buy_box_id: 'box-1' }));

  view.unmount();
  render(<QueryClientProvider client={new QueryClient()}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  expect(screen.getByLabelText('Saved buy box')).toHaveValue('box-1');
  expect(screen.queryByLabelText('Profile')).not.toBeInTheDocument();
  await waitFor(() => expect(apiClient.get).toHaveBeenLastCalledWith('/deals/d/acquisition-screen', { buy_box_id: 'box-1' }));
});

it('surfaces export failure and hides exports from viewers', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ status: 'needs_diligence', counts: { pass: 0, fail: 0, unknown: 1 }, criteria: [] });
  vi.mocked(apiClient.download).mockRejectedValue(new Error('failure'));
  const query = new QueryClient();
  const view = render(<QueryClientProvider client={query}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  await screen.findByText(/Diligence required/);
  fireEvent.click(screen.getByLabelText('Download acquisition screen'));
  expect(await screen.findByRole('alert')).toHaveTextContent('Screen export failed');
  auth.role = 'viewer';
  view.rerender(<QueryClientProvider client={query}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  expect(screen.queryByLabelText('Download acquisition screen')).not.toBeInTheDocument();
});
