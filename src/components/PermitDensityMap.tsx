import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export interface PermitDensityCell {
  id: string;
  latitude: number;
  longitude: number;
  count: number;
  source_coordinate_count: number;
  estimated_count: number;
  south: number;
  west: number;
  north: number;
  east: number;
}

export interface PermitDensityMapProps {
  cells: readonly PermitDensityCell[];
  state: string;
  resetKey?: number;
}

const tiers = [
  { minimum: 1, label: '1-9', color: '#bfdbfe' },
  { minimum: 10, label: '10-49', color: '#60a5fa' },
  { minimum: 50, label: '50-99', color: '#2563eb' },
  { minimum: 100, label: '100+', color: '#1e40af' },
] as const;
const number = new Intl.NumberFormat('en-US');

export function PermitDensityMap({ cells, state, resetKey }: PermitDensityMapProps) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map>();
  const viewport = useRef<{ state: string; resetKey?: number; hasData: boolean } | null>(null);
  const [tileError, setTileError] = useState(false);

  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, { scrollWheelZoom: false, zoomAnimation: false })
      .setView([39, -98], 3);
    map.current = instance;
    const onTileError = () => { if (map.current === instance) setTileError(true); };
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).on('tileerror', onTileError).addTo(instance);
    L.control.scale().addTo(instance);
    const observer = new ResizeObserver(() => {
      if (map.current === instance) instance.invalidateSize({ pan: false, animate: false });
    });
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      tiles.off('tileerror', onTileError);
      map.current = undefined;
      viewport.current = null;
      // Stop deferred map work before a rapid route transition removes the DOM.
      instance.stop();
      instance.remove();
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const group = L.featureGroup().addTo(instance);
    for (const cell of cells) {
      const popup = document.createElement('span');
      popup.textContent = `${state}: ${number.format(cell.count)} stored permits; ${number.format(cell.source_coordinate_count)} source coordinates; ${number.format(cell.estimated_count)} estimated coordinates.`;
      const fillColor = [...tiers].reverse().find(tier => cell.count >= tier.minimum)?.color ?? tiers[0].color;
      L.rectangle([[cell.south, cell.west], [cell.north, cell.east]], {
        color: '#1e40af', weight: 1, fillColor, fillOpacity: 0.65,
      }).bindPopup(popup).addTo(group);
    }
    const previous = viewport.current;
    const changedScope = previous?.state !== state || previous?.resetKey !== resetKey;
    if (cells.length && (changedScope || !previous?.hasData)) {
      instance.fitBounds(group.getBounds(), { padding: [24, 24], maxZoom: 13, animate: false });
    } else if (!cells.length && previous && (changedScope || previous.hasData)) {
      instance.setView([39, -98], 3, { animate: false });
    }
    viewport.current = { state, resetKey, hasData: cells.length > 0 };
    return () => { group.remove(); };
  }, [cells, state, resetKey]);

  return <div className="w-full min-w-0">
    <div className="relative">
      <div ref={element} aria-label={`Permit density map: ${state}`}
        className="relative z-0 h-[360px] w-full sm:h-[480px]" />
      {(tileError || !cells.length) && <p role="status"
        className="pointer-events-none absolute bottom-8 left-3 right-3 z-[400] w-fit max-w-[calc(100%-1.5rem)] rounded border bg-background px-3 py-2 text-sm shadow-sm">
        {tileError ? `Background map unavailable.${cells.length ? '' : ' No mapped permits.'}` : 'No mapped permits'}
      </p>}
    </div>
    <ul aria-label="Stored permits per grid cell" className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
      {tiers.map(tier => <li key={tier.minimum} className="inline-flex items-center gap-1.5">
        <span aria-hidden="true" className="h-3 w-3 shrink-0 rounded-sm border border-black/10" style={{ backgroundColor: tier.color }} />
        <span>{tier.label}</span>
      </li>)}
    </ul>
  </div>;
}

export default PermitDensityMap;
