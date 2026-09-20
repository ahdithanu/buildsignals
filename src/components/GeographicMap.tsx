import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export interface GeographicPoint {
  id: string;
  title: string;
  latitude: number;
  longitude: number;
  kind: 'permit' | 'planning' | 'parcel';
}

export default function GeographicMap({ points, onSelect }: {
  points: GeographicPoint[];
  onSelect: (id: string) => void;
}) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map>();
  const selection = useRef(onSelect);
  selection.current = onSelect;
  const [tileError, setTileError] = useState(false);
  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, { scrollWheelZoom: false }).setView([39, -98], 4);
    map.current = instance;
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).on('tileerror', () => setTileError(true)).addTo(instance);
    L.control.scale().addTo(instance);
    const observer = new ResizeObserver(() => instance.invalidateSize());
    observer.observe(element.current);
    return () => { observer.disconnect(); instance.remove(); map.current = undefined; };
  }, []);
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const group = L.featureGroup().addTo(instance);
    const valid = points.filter(p => Number.isFinite(p.latitude) && Number.isFinite(p.longitude)
      && Math.abs(p.latitude) <= 85 && Math.abs(p.longitude) <= 180);
    for (const point of valid) {
      const label = document.createElement('span');
      label.textContent = point.title;
      L.circleMarker([point.latitude, point.longitude], {
        radius: 8, color: point.kind === 'planning' ? '#047857' : point.kind === 'parcel' ? '#9f1239' : '#1d4ed8',
        fillOpacity: 0.8, weight: 2,
      }).bindTooltip(label).on('click', () => selection.current(point.id)).addTo(group);
    }
    if (valid.length) instance.fitBounds(group.getBounds(), { padding: [35, 35], maxZoom: 14 });
    return () => { group.remove(); };
  }, [points]);
  return <div>
    {tileError && <p role="status" className="p-2 text-sm">Background map unavailable. Record locations and the list remain available.</p>}
    <div ref={element} aria-label="Geographic signal map" className="relative z-0 h-[380px] w-full sm:h-[480px]" />
  </div>;
}
