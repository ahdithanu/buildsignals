import { useId, useState } from 'react';
import { geoAlbersUsa, geoPath } from 'd3-geo';
import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson';
import boundaries from '@/data/us-state-boundaries.json';

export interface NationalPermitState {
  state: string;
  label: string;
  permit_count: number;
  mapped_count: number;
  unmapped_count: number;
}

export interface NationalPermitHeatmapProps {
  states: readonly NationalPermitState[];
  onSelect: (state: string) => void;
}

const tiers = [
  { minimum: 0, label: 'No stored records', color: '#e5e7eb' },
  { minimum: 1, label: '1-99', color: '#bfdbfe' },
  { minimum: 100, label: '100-999', color: '#60a5fa' },
  { minimum: 1000, label: '1,000-4,999', color: '#2563eb' },
  { minimum: 5000, label: '5,000+', color: '#1e40af' },
] as const;
const number = new Intl.NumberFormat('en-US');
const geography = boundaries as FeatureCollection<Polygon | MultiPolygon, { code: string; name: string }>;
const projection = geoAlbersUsa().fitExtent([[16, 16], [984, 604]], geography);
const path = geoPath(projection);
const shapes = geography.features.map(feature => ({
  ...feature.properties, path: path(feature) ?? '',
}));

function colorFor(count: number) {
  return [...tiers].reverse().find(tier => count >= tier.minimum)?.color ?? tiers[0].color;
}

export function NationalPermitHeatmap({ states, onSelect }: NationalPermitHeatmapProps) {
  const id = useId();
  const [hovered, setHovered] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const byState = new Map(states.map(state => [state.state, state]));
  const activeCode = hovered ?? focused;
  const activeShape = shapes.find(shape => shape.code === activeCode);
  const active = activeShape ? byState.get(activeShape.code) ?? {
    label: activeShape.name, permit_count: 0, mapped_count: 0, unmapped_count: 0,
  } : {
    label: 'All states + DC',
    permit_count: states.reduce((sum, state) => sum + state.permit_count, 0),
    mapped_count: states.reduce((sum, state) => sum + state.mapped_count, 0),
    unmapped_count: states.reduce((sum, state) => sum + state.unmapped_count, 0),
  };

  return <figure className="w-full min-w-0">
    <svg viewBox="0 0 1000 620" preserveAspectRatio="xMidYMid meet" role="group"
      aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}
      className="block h-auto w-full" style={{ aspectRatio: '1000 / 620',
        maxHeight: 'min(640px, max(240px, calc(100dvh - 320px)))' }}>
      <title id={`${id}-title`}>Stored permit activity by state</title>
      <desc id={`${id}-description`}>Stored permits include records without mapped coordinates. No stored records does not mean no permit activity.</desc>
      {shapes.map(shape => {
        const counts = byState.get(shape.code);
        const total = counts?.permit_count ?? 0;
        const label = `${counts?.label ?? shape.name}: ${number.format(total)} stored permits, ${number.format(counts?.mapped_count ?? 0)} mapped, ${number.format(counts?.unmapped_count ?? 0)} unmapped`;
        return <path key={shape.code} d={shape.path} fill={colorFor(total)}
          stroke="hsl(var(--background))" strokeWidth={1} vectorEffect="non-scaling-stroke"
          role="button" tabIndex={0} aria-label={label}
          className="cursor-pointer transition-colors hover:stroke-foreground hover:stroke-2 focus:stroke-foreground focus:stroke-[3] focus:outline-none"
          onMouseEnter={() => setHovered(shape.code)} onMouseLeave={() => setHovered(null)}
          onFocus={() => setFocused(shape.code)} onBlur={() => setFocused(null)}
          onClick={() => onSelect(shape.code)} onKeyDown={event => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              if (!event.repeat) onSelect(shape.code);
            }
          }}>
          <title>{label}</title>
        </path>;
      })}
    </svg>
    <figcaption>
      <ul aria-label="Stored permits by state legend" className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
        {tiers.map(tier => <li key={tier.minimum} className="inline-flex items-center gap-1.5">
          <span data-swatch="" aria-hidden="true" className="h-3 w-3 shrink-0 rounded-sm border border-black/10" style={{ backgroundColor: tier.color }} />
          <span>{tier.label}</span>
        </li>)}
      </ul>
      <div role="status" aria-live="polite" aria-atomic="true"
        className="mt-4 grid min-h-[104px] grid-cols-2 items-start gap-x-4 gap-y-2 border-t pt-3 text-sm sm:min-h-[64px] sm:grid-cols-4">
        <span className="break-words font-medium">{active.label}</span>
        {[['Stored permits', active.permit_count], ['Mapped', active.mapped_count], ['Unmapped', active.unmapped_count]].map(([label, value]) =>
          <span key={String(label)} className="min-w-0">
            <span className="block text-xs text-muted-foreground">{label}</span>
            <span className="break-words font-medium tabular-nums">{number.format(Number(value))}</span>
          </span>,
        )}
      </div>
    </figcaption>
  </figure>;
}

export default NationalPermitHeatmap;
