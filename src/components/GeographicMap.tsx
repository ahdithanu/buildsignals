import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export interface GeographicPoint {
  id: string;
  title: string;
  latitude: number;
  longitude: number;
  kind: 'permit' | 'planning' | 'parcel';
  location_method?: 'source_coordinate' | 'census_address_range_estimate';
}

export interface GeographicBoundary {
  id: string;
  title: string;
  geometry: { type: 'Polygon'; coordinates: number[][][] };
}

export default function GeographicMap({ points, boundaries = [], initialCenter, onSelect }: {
  points: GeographicPoint[];
  boundaries?: GeographicBoundary[];
  initialCenter?: { latitude: number; longitude: number; zoom: number };
  onSelect: (id: string) => void;
}) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map>();
  const selection = useRef(onSelect);
  selection.current = onSelect;
  const [tileError, setTileError] = useState(false);
  const initialLatitude = initialCenter?.latitude ?? 39;
  const initialLongitude = initialCenter?.longitude ?? -98;
  const initialZoom = initialCenter?.zoom ?? 4;
  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, { scrollWheelZoom: false }).setView([initialLatitude, initialLongitude], initialZoom);
    map.current = instance;
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).on('tileerror', () => setTileError(true)).addTo(instance);
    L.control.scale().addTo(instance);
    const observer = new ResizeObserver(() => instance.invalidateSize());
    observer.observe(element.current);
    return () => { observer.disconnect(); instance.remove(); map.current = undefined; };
  }, [initialLatitude, initialLongitude, initialZoom]);
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const group = L.featureGroup().addTo(instance);
    const valid = points.filter(p => Number.isFinite(p.latitude) && Number.isFinite(p.longitude)
      && Math.abs(p.latitude) <= 85 && Math.abs(p.longitude) <= 180);
    for (const boundary of boundaries) {
      if (boundary.geometry.type !== 'Polygon') continue;
      const rings = boundary.geometry.coordinates.map(ring => ring.map(pair =>
        Array.isArray(pair) && pair.length >= 2 && Number.isFinite(pair[0]) && Number.isFinite(pair[1])
          && Math.abs(pair[0]) <= 180 && Math.abs(pair[1]) <= 85
          ? [pair[1], pair[0]] as L.LatLngTuple : null,
      ));
      if (!rings.length || rings.some(ring => ring.length < 4 || ring.some(pair => !pair))) continue;
      const label = document.createElement('span');
      label.textContent = boundary.title;
      L.polygon(rings as L.LatLngTuple[][], { color: '#0f766e', weight: 2, fillOpacity: 0.22 })
        .bindTooltip(label).on('click', () => selection.current(boundary.id)).addTo(group);
    }
    const grouped = new Map<string, GeographicPoint[]>();
    for (const point of valid) {
      const key = `${point.kind}:${point.latitude}:${point.longitude}:${point.location_method || ''}`;
      grouped.set(key, [...(grouped.get(key) ?? []), point]);
    }
    for (const groupPoints of grouped.values()) {
      const point = groupPoints[0];
      const label = document.createElement('span');
      label.textContent = groupPoints.length > 1 ? `${groupPoints.length} ${point.kind} records at this coordinate` : point.title;
      const marker = L.circleMarker([point.latitude, point.longitude], {
        radius: groupPoints.length > 1 ? 14 : 8,
        color: point.kind === 'planning' ? '#047857' : point.kind === 'parcel' ? '#9f1239' : point.location_method === 'census_address_range_estimate' ? '#a16207' : '#1d4ed8',
        fillOpacity: 0.8, weight: 2,
      }).bindPopup(label).on('click', () => selection.current(point.id)).addTo(group);
      if (groupPoints.length > 1) marker.bindTooltip(String(groupPoints.length), {
        permanent: true, direction: 'center', className: 'geographic-map-count',
      });
    }
    if (group.getLayers().length) instance.fitBounds(group.getBounds(), { padding: [35, 35], maxZoom: 14 });
    return () => { group.remove(); };
  }, [points, boundaries]);
  return <div>
    {tileError && <p role="status" className="p-2 text-sm">Background map unavailable. Record locations and the list remain available.</p>}
    <div ref={element} aria-label="Geographic signal map" className="relative z-0 h-[380px] w-full sm:h-[480px]" />
  </div>;
}
