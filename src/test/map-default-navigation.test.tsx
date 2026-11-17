import { fireEvent, render, screen } from '@testing-library/react';
import { Link, MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import AcquisitionMap from '@/pages/AcquisitionMap';

vi.mock('@/components/Layout', () => ({ Layout: ({ children }: { children: React.ReactNode }) => <><Link to="/map">Map</Link>{children}</> }));
vi.mock('@/components/PermitActivityExplorer', () => ({ PermitActivityExplorer: ({ state, onStateChange }: { state: string; onStateChange: (value: string) => void }) =>
  <section><h1>National permit activity</h1><output aria-label="Activity state">{state || 'all'}</output><button onClick={() => onStateChange('TX')}>Texas activity</button><button onClick={() => onStateChange('FL')}>Florida activity</button><button onClick={() => onStateChange('')}>All states</button></section> }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ role: 'viewer' }) }));
vi.mock('@/hooks/useAcquisitionRadar', () => ({ useAcquisitionRadar: () => ({ data: { items: [] }, exportSearch: {} }), useZip3Heatmap: () => ({}) }));
vi.mock('@/components/MapReadiness', () => ({ MapReadiness: () => <p>Parcel diagnostics</p> }));
vi.mock('@/components/CoverageMapExplorer', () => ({ CoverageMapExplorer: ({ state }: { state: string }) => <p>Inventory {state}</p> }));
vi.mock('@/components/SignalMapExplorer', () => ({ SignalMapExplorer: ({ onStateChange, onRecordSelect }: {
  onStateChange: (state: string) => void; onRecordSelect: (record: unknown) => void;
}) => {
  return <><p>Filing pins</p>
    <button onClick={() => onStateChange('TX')}>Texas filings</button>
    <button onClick={() => onRecordSelect({ kind: 'permit', id: 'permit:sf-estimate', title: 'SF estimate',
      latitude: 37.79, longitude: -122.4, location_method: 'census_address_range_estimate' })}>Select SF estimate</button></>;
} }));
function Controls() {
  const location = useLocation(); const navigate = useNavigate();
  return <><output aria-label="Map URL">{location.pathname}{location.search}</output><button onClick={() => navigate(-1)}>Back</button><button onClick={() => navigate(1)}>Forward</button></>;
}
function mount(entry = '/map') { return render(<MemoryRouter initialEntries={[entry]}><AcquisitionMap /><Controls /></MemoryRouter>); }
beforeEach(() => { vi.spyOn(window, 'scrollTo'); });
afterEach(() => { vi.restoreAllMocks(); });
it('opens all states without parcel empty states or sampled filing pins', () => {
  mount(); expect(screen.getByRole('heading', { name: 'National permit activity' })).toBeVisible();
  expect(screen.getByLabelText('Activity state')).toHaveTextContent('all');
  expect(screen.queryByText('No ranked parcels yet')).not.toBeInTheDocument();
  expect(screen.queryByText('Parcel diagnostics')).not.toBeInTheDocument();
  expect(screen.queryByText('Filing pins')).not.toBeInTheDocument();
  expect(window.scrollTo).toHaveBeenLastCalledWith({ top: 0, left: 0, behavior: 'instant' });
});
it('treats the URL as authoritative across state changes, Map navigation, back and forward', () => {
  mount(); fireEvent.click(screen.getByText('Texas activity'));
  expect(screen.getByLabelText('Map URL')).toHaveTextContent('/map?state=TX');
  fireEvent.click(screen.getByText('Florida activity'));
  fireEvent.click(screen.getByText('Map'));
  expect(screen.getByLabelText('Activity state')).toHaveTextContent('all');
  expect(screen.getByLabelText('Map URL')).toHaveTextContent(/^\/map$/);
  fireEvent.click(screen.getByText('Back')); expect(screen.getByLabelText('Activity state')).toHaveTextContent('FL');
  fireEvent.click(screen.getByText('Back')); expect(screen.getByLabelText('Activity state')).toHaveTextContent('TX');
  fireEvent.click(screen.getByText('Forward')); expect(screen.getByLabelText('Activity state')).toHaveTextContent('FL');
});
it('restores only an explicit shared state and resets it without any remembered region', () => {
  mount('/map?state=CA'); expect(screen.getByLabelText('Activity state')).toHaveTextContent('CA');
  fireEvent.click(screen.getByText('All states')); expect(screen.getByLabelText('Map URL')).toHaveTextContent(/^\/map$/);
});
it('keeps inventory a secondary explicit view and Map navigation returns to national activity', () => {
  mount('/map?view=coverage&state=FL'); expect(screen.getByText('Inventory FL')).toBeVisible();
  fireEvent.click(screen.getByText('Map')); expect(screen.getByLabelText('Activity state')).toHaveTextContent('all');
});
it('resets source selections when browser history changes state scope', () => {
  mount('/map?view=filings&state=CA');
  fireEvent.click(screen.getByText('Select SF estimate'));
  expect(screen.getByText('Estimated location only')).toBeVisible();
  fireEvent.click(screen.getByText('Texas filings'));
  expect(screen.queryByText('Estimated location only')).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('Back'));
  expect(screen.getByLabelText('Map URL')).toHaveTextContent('state=CA');
  expect(screen.queryByText('Estimated location only')).not.toBeInTheDocument();
});
it('does not reset page scroll on a rerender with the same map scope', () => {
  const view = mount('/map?state=TX');
  vi.mocked(window.scrollTo).mockClear();
  view.rerender(<MemoryRouter initialEntries={['/map?state=TX']}><AcquisitionMap /><Controls /></MemoryRouter>);
  expect(window.scrollTo).not.toHaveBeenCalled();
});
