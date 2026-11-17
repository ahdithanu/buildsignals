import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { geoAlbersUsa, geoPath } from 'd3-geo';
import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson';
import NationalPermitHeatmap from '@/components/NationalPermitHeatmap';
import boundaries from '@/data/us-state-boundaries.json';

const counts = (state: string, label: string, permit_count: number, mapped_count = 0) => ({
  state, label, permit_count, mapped_count, unmapped_count: permit_count - mapped_count,
});

describe('NationalPermitHeatmap', () => {
  it('renders all 50 states and DC as distinct nonblank geographic paths, including Alaska and Hawaii', () => {
    const { container } = render(<NationalPermitHeatmap states={[]} onSelect={vi.fn()} />);
    const svg = screen.getByRole('group', { name: 'Stored permit activity by state' });
    expect(svg).toHaveAttribute('viewBox', '0 0 1000 620');
    const states = within(svg).getAllByRole('button');
    expect(states).toHaveLength(51);
    const paths = states.map(state => state.getAttribute('d'));
    expect(paths.every(path => path?.startsWith('M') && !/NaN|Infinity/.test(path))).toBe(true);
    expect(new Set(paths).size).toBe(51);
    for (const name of ['Alaska', 'Hawaii', 'District of Columbia']) {
      expect(within(svg).getByRole('button', { name: `${name}: 0 stored permits, 0 mapped, 0 unmapped` }))
        .toHaveAttribute('tabindex', '0');
    }
    expect(container.querySelectorAll('circle')).toHaveLength(0);
    expect(screen.getByText('No stored records')).toBeInTheDocument();
  });

  it('projects the actual supplied geometry within the frame with real Alaska and Hawaii insets', () => {
    render(<NationalPermitHeatmap states={[]} onSelect={vi.fn()} />);
    const geography = boundaries as FeatureCollection<Polygon | MultiPolygon, { code: string; name: string }>;
    const projected = geoPath(geoAlbersUsa().fitExtent([[16, 16], [984, 604]], geography));
    for (const feature of geography.features) {
      const shape = screen.getByRole('button', { name: `${feature.properties.name}: 0 stored permits, 0 mapped, 0 unmapped` });
      expect(shape.getAttribute('d')).toBe(projected(feature));
      expect(projected.area(feature)).toBeGreaterThan(0);
      const [[west, north], [east, south]] = projected.bounds(feature);
      expect(west).toBeGreaterThanOrEqual(15.99);
      expect(east).toBeLessThanOrEqual(984.01);
      expect(north).toBeGreaterThanOrEqual(16);
      expect(south).toBeLessThanOrEqual(604);
      if (['AK', 'HI'].includes(feature.properties.code)) {
        expect(east).toBeLessThan(400);
        expect(north).toBeGreaterThan(450);
      }
    }
  });

  it('colors total stored permit counts, including unmapped records, with fixed legend tiers', () => {
    render(<NationalPermitHeatmap states={[
      counts('CA', 'California', 5000, 1), counts('FL', 'Florida', 4999),
      counts('TX', 'Texas', 999), counts('NY', 'New York', 99),
    ]} onSelect={vi.fn()} />);
    const state = (name: string) => screen.getByRole('button', { name: new RegExp(`^${name}:`) });
    const fills = ['California', 'Florida', 'Texas', 'New York', 'Alaska']
      .map(name => state(name).getAttribute('fill'));
    expect(new Set(fills).size).toBe(5);
    for (const tier of ['1-99', '100-999', '1,000-4,999', '5,000+']) {
      expect(screen.getByText(tier)).toBeInTheDocument();
    }
    expect(screen.getByRole('status')).toHaveTextContent('11,097');
    fireEvent.mouseEnter(state('California'));
    const info = screen.getByRole('status');
    expect(info).toHaveTextContent('California');
    expect(info).toHaveTextContent('5,000');
    expect(info).toHaveTextContent('4,999');
    expect(state('California').querySelector('title')).toHaveTextContent('5,000 stored permits, 1 mapped, 4,999 unmapped');
  });

  it.each([[1, '1-99'], [99, '1-99'], [100, '100-999'], [999, '100-999'],
    [1000, '1,000-4,999'], [4999, '1,000-4,999'], [5000, '5,000+']])(
    'assigns count %s to legend tier %s', (count, tier) => {
      render(<NationalPermitHeatmap states={[counts('CA', 'California', Number(count))]} onSelect={vi.fn()} />);
      const state = screen.getByRole('button', { name: /^California:/ });
      const legend = screen.getByText(String(tier)).parentElement;
      expect(legend?.querySelector('[data-swatch]')).toHaveStyle({ backgroundColor: state.getAttribute('fill') });
    },
  );

  it('selects zero-count states by click, Enter and Space and exposes focused counts', () => {
    const onSelect = vi.fn();
    render(<NationalPermitHeatmap states={[]} onSelect={onSelect} />);
    const alaska = screen.getByRole('button', { name: /^Alaska:/ });
    fireEvent.focus(alaska);
    expect(screen.getByRole('status')).toHaveTextContent('Alaska');
    fireEvent.keyDown(alaska, { key: 'Enter' });
    fireEvent.keyDown(alaska, { key: ' ' });
    fireEvent.click(alaska);
    fireEvent.keyDown(alaska, { key: 'ArrowRight' });
    expect(onSelect.mock.calls).toEqual([['AK'], ['AK'], ['AK']]);
  });

  it('uses the latest counts and selection callback without injecting label HTML', () => {
    const oldSelect = vi.fn();
    const newSelect = vi.fn();
    const { rerender, container } = render(<NationalPermitHeatmap states={[counts('CA', 'California', 1)]} onSelect={oldSelect} />);
    fireEvent.focus(screen.getByRole('button', { name: /^California:/ }));
    rerender(<NationalPermitHeatmap states={[counts('CA', '<img src=x onerror=alert(1)>', 42, 10)]} onSelect={newSelect} />);
    expect(screen.getByRole('status')).toHaveTextContent('<img src=x onerror=alert(1)>');
    expect(screen.getByRole('status')).toHaveTextContent('32');
    expect(container.querySelector('img')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /42 stored permits/ }));
    expect(newSelect).toHaveBeenCalledWith('CA');
    expect(oldSelect).not.toHaveBeenCalled();
  });

  it('returns to the focused state counts when pointer hover ends', () => {
    render(<NationalPermitHeatmap states={[counts('FL', 'Florida', 100, 25)]} onSelect={vi.fn()} />);
    fireEvent.focus(screen.getByRole('button', { name: /^Florida:/ }));
    const hawaii = screen.getByRole('button', { name: /^Hawaii:/ });
    fireEvent.mouseEnter(hawaii);
    expect(screen.getByRole('status')).toHaveTextContent('Hawaii');
    fireEvent.mouseLeave(hawaii);
    expect(screen.getByRole('status')).toHaveTextContent('Florida');
    expect(screen.getByRole('status')).toHaveTextContent('75');
  });

  it('does not fetch a separate inventory and keeps accessible IDs unique across maps', () => {
    const fetch = vi.spyOn(globalThis, 'fetch');
    const { container } = render(<>
      <NationalPermitHeatmap states={[]} onSelect={vi.fn()} />
      <NationalPermitHeatmap states={[]} onSelect={vi.fn()} />
    </>);
    const ids = [...container.querySelectorAll('[id]')].map(element => element.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockRestore();
  });
});
