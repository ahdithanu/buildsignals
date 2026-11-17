import { StrictMode } from 'react';
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PermitDensityMap, { type PermitDensityCell } from '@/components/PermitDensityMap';

const fake = vi.hoisted(() => ({
  maps: [] as Array<Record<string, ReturnType<typeof vi.fn>>>,
  groups: [] as Array<Record<string, ReturnType<typeof vi.fn>>>,
  rectangles: [] as Array<{ bounds: unknown; options: unknown; popup?: HTMLElement; group?: unknown }>,
  resizes: [] as Array<() => void>,
  tileErrors: [] as Array<() => void>,
  disconnect: vi.fn(),
  tileOff: vi.fn(),
  createMap: vi.fn(),
}));

vi.mock('leaflet', () => ({ default: {
  map: (...args: unknown[]) => {
    fake.createMap(...args);
    const map = { setView: vi.fn(), invalidateSize: vi.fn(), stop: vi.fn(), remove: vi.fn(), fitBounds: vi.fn() };
    map.setView.mockReturnValue(map);
    fake.maps.push(map);
    return map;
  },
  tileLayer: () => {
    const tile = { on: vi.fn(), off: fake.tileOff, addTo: vi.fn() };
    tile.on.mockImplementation((_event, callback) => { fake.tileErrors.push(callback); return tile; });
    tile.addTo.mockReturnValue(tile);
    return tile;
  },
  control: { scale: () => ({ addTo: vi.fn() }) },
  featureGroup: () => {
    const group = { addTo: vi.fn(), getBounds: vi.fn(() => ({ group: fake.groups.length })), remove: vi.fn() };
    group.addTo.mockReturnValue(group);
    fake.groups.push(group);
    return group;
  },
  rectangle: (bounds: unknown, options: unknown) => {
    const record = { bounds, options } as (typeof fake.rectangles)[number];
    fake.rectangles.push(record);
    const rectangle = {
      bindPopup: (popup: HTMLElement) => { record.popup = popup; return rectangle; },
      addTo: (group: unknown) => { record.group = group; return rectangle; },
    };
    return rectangle;
  },
} }));

const cell: PermitDensityCell = {
  id: 'FL:one', latitude: 28.5, longitude: -81.25, count: 42,
  source_coordinate_count: 30, estimated_count: 12,
  south: 28.4, west: -81.4, north: 28.6, east: -81.1,
};

describe('PermitDensityMap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fake.maps.length = 0;
    fake.groups.length = 0;
    fake.rectangles.length = 0;
    fake.resizes.length = 0;
    fake.tileErrors.length = 0;
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { fake.resizes.push(callback); }
      observe() {}
      disconnect = fake.disconnect;
    });
  });

  it('renders real cell bounds with source/estimate counts as safe popup text', () => {
    render(<PermitDensityMap cells={[cell]} state={'<img src=x onerror=alert(1)>'} />);
    expect(fake.rectangles[0].bounds).toEqual([[28.4, -81.4], [28.6, -81.1]]);
    expect(fake.rectangles[0].popup).toBeInstanceOf(HTMLElement);
    expect(fake.rectangles[0].popup?.textContent).toContain('42 stored permits');
    expect(fake.rectangles[0].popup?.textContent).toContain('30 source coordinates');
    expect(fake.rectangles[0].popup?.textContent).toContain('12 estimated coordinates');
    expect(fake.rectangles[0].popup?.querySelector('img')).toBeNull();
    expect(fake.maps[0].fitBounds).toHaveBeenCalledOnce();
    expect(fake.maps[0].fitBounds).toHaveBeenCalledWith(fake.groups[0].getBounds.mock.results[0].value, expect.objectContaining({ animate: false }));
    expect(screen.getByLabelText(/Permit density map/)).toHaveClass('h-[360px]', 'sm:h-[480px]');
  });

  it('updates cells without refitting or recreating the map during same-state refreshes', () => {
    const { rerender } = render(<PermitDensityMap cells={[cell]} state="FL" />);
    rerender(<PermitDensityMap cells={[{ ...cell, count: 50, north: 28.8 }]} state="FL" />);
    expect(fake.createMap).toHaveBeenCalledOnce();
    expect(fake.maps[0].fitBounds).toHaveBeenCalledOnce();
    expect(fake.maps[0].setView).toHaveBeenCalledOnce();
    expect(fake.groups[0].remove).toHaveBeenCalledOnce();
    expect(fake.rectangles[1].bounds).toEqual([[28.4, -81.4], [28.8, -81.1]]);
  });

  it('uses fixed count tiers for cell colors instead of normalizing each refresh', () => {
    const { rerender } = render(<PermitDensityMap cells={[cell]} state="FL" />);
    const initial = fake.rectangles[0].options;
    rerender(<PermitDensityMap cells={[cell, { ...cell, id: 'FL:two', count: 5000 }]} state="FL" />);
    expect(fake.rectangles[1].options).toEqual(initial);
    expect(fake.rectangles[2].options).not.toEqual(initial);
  });

  it('refits on a state change and removes all prior-state layers before adding new ones', () => {
    const { rerender } = render(<PermitDensityMap cells={[cell]} state="FL" />);
    const california = { ...cell, id: 'CA:one', south: 37, west: -123, north: 38, east: -122 };
    rerender(<PermitDensityMap cells={[california]} state="CA" />);
    expect(fake.maps[0].fitBounds).toHaveBeenCalledTimes(2);
    expect(fake.groups[0].remove).toHaveBeenCalledOnce();
    expect(fake.groups[0].remove.mock.invocationCallOrder[0])
      .toBeLessThan(fake.groups[1].addTo.mock.invocationCallOrder[0]);
    expect(fake.rectangles[1].bounds).toEqual([[37, -123], [38, -122]]);
    expect(fake.rectangles[1].group).toBe(fake.groups[1]);
  });

  it('fits the first arriving data and supports an explicit viewport reset', () => {
    const { rerender } = render(<PermitDensityMap cells={[]} state="FL" />);
    expect(fake.maps[0].fitBounds).not.toHaveBeenCalled();
    rerender(<PermitDensityMap cells={[cell]} state="FL" />);
    expect(fake.maps[0].fitBounds).toHaveBeenCalledOnce();
    rerender(<PermitDensityMap cells={[cell]} state="FL" resetKey={1} />);
    expect(fake.maps[0].fitBounds).toHaveBeenCalledTimes(2);
    rerender(<PermitDensityMap cells={[{ ...cell, count: 50 }]} state="FL" resetKey={1} />);
    expect(fake.maps[0].fitBounds).toHaveBeenCalledTimes(2);
  });

  it('resets an empty new scope to the US fallback instead of keeping the prior state extent', () => {
    const { rerender } = render(<PermitDensityMap cells={[cell]} state="FL" />);
    rerender(<PermitDensityMap cells={[]} state="AK" />);
    expect(fake.groups[0].remove).toHaveBeenCalledOnce();
    expect(fake.rectangles).toHaveLength(1);
    expect(fake.maps[0].setView).toHaveBeenLastCalledWith([39, -98], 3, { animate: false });
    expect(screen.getByText('No mapped permits')).toBeInTheDocument();
    rerender(<PermitDensityMap cells={[]} state="AK" />);
    expect(fake.maps[0].setView).toHaveBeenCalledTimes(2);
  });

  it('clears the viewport when the same state loses its last cell, then fits newly arriving data', () => {
    const { rerender } = render(<PermitDensityMap cells={[cell]} state="FL" />);
    rerender(<PermitDensityMap cells={[]} state="FL" />);
    expect(fake.maps[0].setView).toHaveBeenCalledTimes(2);
    expect(fake.groups[0].remove).toHaveBeenCalledOnce();
    rerender(<PermitDensityMap cells={[cell]} state="FL" />);
    expect(fake.maps[0].fitBounds).toHaveBeenCalledTimes(2);
  });

  it('stops before removing and ignores queued resize/tile callbacks after unmount', () => {
    const { unmount } = render(<PermitDensityMap cells={[cell]} state="FL" />);
    expect(fake.createMap).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ zoomAnimation: false }));
    act(() => fake.resizes[0]());
    expect(fake.maps[0].invalidateSize).toHaveBeenCalledOnce();
    unmount();
    act(() => { fake.resizes[0](); fake.tileErrors[0](); });
    expect(fake.maps[0].invalidateSize).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
    expect(fake.tileOff).toHaveBeenCalledWith('tileerror', expect.any(Function));
    expect(fake.maps[0].stop.mock.invocationCallOrder[0]).toBeLessThan(fake.maps[0].remove.mock.invocationCallOrder[0]);
    expect(fake.groups[0].remove).toHaveBeenCalledOnce();
  });

  it('survives StrictMode remounts without reusing a removed map or stale callbacks', () => {
    const { unmount } = render(<StrictMode><PermitDensityMap cells={[cell]} state="HI" /></StrictMode>);
    expect(fake.maps).toHaveLength(2);
    act(() => { fake.resizes[0](); fake.tileErrors[0](); });
    expect(fake.maps[0].invalidateSize).not.toHaveBeenCalled();
    expect(fake.maps[1].fitBounds).toHaveBeenCalledOnce();
    act(() => fake.resizes[1]());
    expect(fake.maps[1].invalidateSize).toHaveBeenCalledOnce();
    unmount();
    expect(fake.maps.every(map => map.remove.mock.calls.length === 1)).toBe(true);
  });

  it('keeps grid layers visible when background tiles fail', () => {
    render(<PermitDensityMap cells={[cell]} state="FL" />);
    act(() => fake.tileErrors[0]());
    expect(screen.getByRole('status')).toHaveTextContent('Background map unavailable');
    expect(fake.groups[0].remove).not.toHaveBeenCalled();
  });
});
