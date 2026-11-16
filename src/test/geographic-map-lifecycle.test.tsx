import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import GeographicMap from '@/components/GeographicMap';

const fake = vi.hoisted(() => {
  const map = { setView: vi.fn(), invalidateSize: vi.fn(), stop: vi.fn(), remove: vi.fn(), fitBounds: vi.fn() };
  map.setView.mockReturnValue(map);
  const group = { addTo: vi.fn(), getLayers: vi.fn(() => [1]), getBounds: vi.fn(() => 'bounds'), remove: vi.fn() };
  group.addTo.mockReturnValue(group);
  const marker = { bindPopup: vi.fn(), on: vi.fn(), addTo: vi.fn(), bindTooltip: vi.fn() };
  marker.bindPopup.mockReturnValue(marker);
  marker.on.mockReturnValue(marker);
  marker.addTo.mockReturnValue(marker);
  return { map, group, marker, createMap: vi.fn(() => map), resize: null as null | (() => void), disconnect: vi.fn() };
});
vi.mock('leaflet', () => ({ default: {
  map: fake.createMap,
  tileLayer: () => ({ on: () => ({ addTo: vi.fn() }) }),
  control: { scale: () => ({ addTo: vi.fn() }) },
  featureGroup: () => fake.group,
  circleMarker: () => fake.marker,
} }));

describe('geographic map lifetime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { fake.resize = callback; }
      observe() {}
      disconnect = fake.disconnect;
    });
  });
  it('avoids deferred zoom transitions and stops the map before removing its DOM', () => {
    const { unmount } = render(<GeographicMap points={[{ id: 'coverage:FL', title: 'Florida aggregate',
      kind: 'heat', count: 144, latitude: 28.46, longitude: -81.27 }]} onSelect={vi.fn()} />);
    expect(fake.createMap).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ zoomAnimation: false }));
    expect(fake.map.fitBounds).toHaveBeenCalledWith('bounds', expect.objectContaining({ animate: false }));
    expect(fake.marker.bindTooltip).toHaveBeenCalledWith('144', expect.objectContaining({ permanent: true }));
    unmount();
    expect(fake.map.stop).toHaveBeenCalledOnce();
    expect(fake.map.stop.mock.invocationCallOrder[0]).toBeLessThan(fake.map.remove.mock.invocationCallOrder[0]);
  });
  it('ignores an already queued ResizeObserver callback after teardown', () => {
    const { unmount } = render(<GeographicMap points={[]} onSelect={vi.fn()} />);
    fake.resize?.();
    expect(fake.map.invalidateSize).toHaveBeenCalledOnce();
    unmount();
    fake.resize?.();
    expect(fake.map.invalidateSize).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
  });
  it('sums co-located aggregate groups rather than showing only the first count', () => {
    render(<GeographicMap points={[
      { id: 'one', title: 'One', kind: 'heat', count: 3, latitude: 28, longitude: -81 },
      { id: 'two', title: 'Two', kind: 'heat', count: 5, latitude: 28, longitude: -81 },
    ]} onSelect={vi.fn()} />);
    expect(fake.marker.bindTooltip).toHaveBeenCalledWith('8', expect.objectContaining({ permanent: true }));
    expect(fake.marker.bindPopup.mock.calls[0][0].textContent).toBe('8 mapped records across 2 geographic groups');
  });
});
