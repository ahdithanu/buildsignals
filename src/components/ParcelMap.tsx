import { useMemo } from 'react';
import { MapPinned, Map as MapIcon, Target } from 'lucide-react';
import { cn } from '@/lib/utils';

type ParcelMapPointTone = 'anchor' | 'candidate' | 'highlight';

export interface ParcelMapPoint {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  tone?: ParcelMapPointTone;
  subtitle?: string;
  href?: string;
  score?: number;
  distanceMiles?: number;
  boundary?: unknown;
}

export interface ParcelMapCenter {
  label: string;
  latitude: number;
  longitude: number;
  subtitle?: string;
  href?: string;
}

export interface ParcelMapProps {
  center: ParcelMapCenter;
  points?: ParcelMapPoint[];
  boundary?: unknown;
  radiusMiles?: number;
  title?: string;
  subtitle?: string;
  className?: string;
  emptyLabel?: string;
}

type BoundaryRing = Array<[number, number]>;

const VIEWBOX_WIDTH = 420;
const VIEWBOX_HEIGHT = 300;
const VIEWBOX_PADDING = 24;

function getObjectValue(source: unknown, key: string): unknown {
  if (!source || typeof source !== 'object') return undefined;
  if (Array.isArray(source)) return undefined;
  return (source as Record<string, unknown>)[key];
}

function extractBoundaryRings(boundary: unknown): BoundaryRing[] {
  const geometry = getObjectValue(boundary, 'geometry') ?? boundary;
  if (!geometry || typeof geometry !== 'object' || Array.isArray(geometry)) return [];

  const type = String(getObjectValue(geometry, 'type') ?? '').toLowerCase();
  const coordinates = getObjectValue(geometry, 'coordinates');
  const rings = getObjectValue(geometry, 'rings');
  if (!coordinates && Array.isArray(rings)) {
    const arcgisRings = rings as unknown[];
    return arcgisRings
      .map((ring) => Array.isArray(ring)
        ? ring.map((pair) => Array.isArray(pair) && pair.length >= 2 ? [Number(pair[0]), Number(pair[1])] as [number, number] : null).filter((value): value is [number, number] => value !== null)
        : [])
      .filter((ring) => ring.length > 0);
  }
  if (!coordinates) return [];

  const polygons: unknown[] = [];
  if (type === 'featurecollection') {
    const features = Array.isArray(getObjectValue(geometry, 'features')) ? getObjectValue(geometry, 'features') as unknown[] : [];
    const firstFeature = features[0];
    if (firstFeature) {
      polygons.push(...extractBoundaryRings(getObjectValue(firstFeature, 'geometry') ?? firstFeature));
    }
    return polygons;
  }
  if (type === 'feature') {
    return extractBoundaryRings(getObjectValue(geometry, 'geometry'));
  }
  if (type === 'multipolygon') {
    const polys = coordinates as unknown[];
    const firstPolygon = polys[0];
    if (!Array.isArray(firstPolygon)) return [];
    const ring = firstPolygon[0];
    if (!Array.isArray(ring)) return [];
    return [ring
      .map((pair) => Array.isArray(pair) && pair.length >= 2 ? [Number(pair[0]), Number(pair[1])] as [number, number] : null)
      .filter((value): value is [number, number] => value !== null)];
  }
  if (type === 'polygon') {
    const rings = coordinates as unknown[];
    return rings
      .map((ring) => Array.isArray(ring)
        ? ring.map((pair) => Array.isArray(pair) && pair.length >= 2 ? [Number(pair[0]), Number(pair[1])] as [number, number] : null).filter((value): value is [number, number] => value !== null)
        : [])
      .filter((ring) => ring.length > 0);
  }
  return [];
}

function projectCoordinate(
  latitude: number,
  longitude: number,
  centerLatitude: number,
  centerLongitude: number,
) {
  const latitudeMiles = 69.0;
  const longitudeMiles = 69.172 * Math.max(Math.cos(centerLatitude * Math.PI / 180), 0.01);
  return {
    x: (longitude - centerLongitude) * longitudeMiles,
    y: (latitude - centerLatitude) * latitudeMiles,
  };
}

function toSvgPoint(
  projected: { x: number; y: number },
  radiusMiles: number,
) {
  const contentWidth = VIEWBOX_WIDTH - VIEWBOX_PADDING * 2;
  const contentHeight = VIEWBOX_HEIGHT - VIEWBOX_PADDING * 2;
  const scale = Math.min(contentWidth, contentHeight) / (radiusMiles * 2 || 1);
  return {
    x: VIEWBOX_WIDTH / 2 + projected.x * scale,
    y: VIEWBOX_HEIGHT / 2 - projected.y * scale,
  };
}

function toneClasses(tone: ParcelMapPointTone | undefined) {
  switch (tone) {
    case 'anchor':
      return 'bg-primary text-primary-foreground ring-4 ring-primary/10';
    case 'highlight':
      return 'bg-emerald-600 text-white ring-4 ring-emerald-500/15';
    default:
      return 'bg-foreground text-background ring-4 ring-background/50';
  }
}

function boundaryStyles(tone: ParcelMapPointTone | undefined) {
  switch (tone) {
    case 'anchor':
      return { fill: 'rgba(59, 130, 246, 0.12)', stroke: 'rgba(59, 130, 246, 0.75)' };
    case 'highlight':
      return { fill: 'rgba(34, 197, 94, 0.16)', stroke: 'rgba(34, 197, 94, 0.85)' };
    default:
      return { fill: 'rgba(15, 23, 42, 0.08)', stroke: 'rgba(15, 23, 42, 0.35)' };
  }
}

function ringsToPaths(
  rings: BoundaryRing[],
  centerLatitude: number,
  centerLongitude: number,
  extentMiles: number,
) {
  return rings.map((ring) => {
    const path = ring
      .map(([longitude, latitude], index) => {
        const point = toSvgPoint(
          projectCoordinate(latitude, longitude, centerLatitude, centerLongitude),
          extentMiles,
        );
        return `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
      })
      .join(' ');
    return `${path} Z`;
  });
}

export function ParcelMap({
  center,
  points = [],
  boundary,
  radiusMiles,
  title = 'Map',
  subtitle,
  className,
  emptyLabel = 'Boundary data is not attached yet.',
}: ParcelMapProps) {
  const primaryRings = useMemo(() => extractBoundaryRings(boundary), [boundary]);
  const pointBoundaries = useMemo(
    () => points.flatMap((point) => {
      const rings = extractBoundaryRings(point.boundary);
      return rings.map((ring, ringIndex) => ({
        id: `${point.id}-${ringIndex}`,
        tone: point.tone,
        ring,
      }));
    }),
    [points],
  );
  const allBoundaryRings = useMemo(
    () => [
      ...primaryRings,
      ...pointBoundaries.map((entry) => entry.ring),
    ],
    [pointBoundaries, primaryRings],
  );
  const projectedBoundary = useMemo(
    () => allBoundaryRings.flatMap((ring) => ring.map(([longitude, latitude]) => projectCoordinate(
      latitude,
      longitude,
      center.latitude,
      center.longitude,
    ))),
    [allBoundaryRings, center.latitude, center.longitude],
  );
  const projectedPoints = useMemo(
    () => points.map((point) => ({
      ...point,
      projected: projectCoordinate(point.latitude, point.longitude, center.latitude, center.longitude),
    })),
    [center.latitude, center.longitude, points],
  );
  const extentMiles = useMemo(() => {
    const projectedRanges = [...projectedBoundary, ...projectedPoints.map((point) => point.projected)];
    const furthest = projectedRanges.reduce((max, point) => Math.max(max, Math.abs(point.x), Math.abs(point.y)), 0);
    return Math.max(radiusMiles ?? 0, furthest * 1.15, 0.35);
  }, [projectedBoundary, projectedPoints, radiusMiles]);
  const centerPoint = toSvgPoint({ x: 0, y: 0 }, extentMiles);
  const primaryBoundaryPaths = ringsToPaths(primaryRings, center.latitude, center.longitude, extentMiles);
  const pointBoundaryPaths = pointBoundaries.flatMap((entry) => {
    const styles = boundaryStyles(entry.tone);
    return ringsToPaths([entry.ring], center.latitude, center.longitude, extentMiles).map((path) => ({
      id: entry.id,
      path,
      ...styles,
    }));
  });
  const hasBoundary = primaryBoundaryPaths.length > 0 || pointBoundaryPaths.length > 0;

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <MapIcon className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          </div>
          {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1">
            <Target className="h-3.5 w-3.5" />
            Center
          </span>
          {hasBoundary ? (
            <span className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1">
              <span className="h-2 w-2 rounded-full bg-emerald-600" />
              Boundary
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1">
              <span className="h-2 w-2 rounded-full bg-muted-foreground" />
              No boundary
            </span>
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-md border bg-background">
        <svg viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`} className="block h-auto w-full">
          <defs>
            <pattern id="parcel-map-grid" width="36" height="36" patternUnits="userSpaceOnUse">
              <path d="M 36 0 L 0 0 0 36" fill="none" stroke="currentColor" strokeOpacity="0.08" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width={VIEWBOX_WIDTH} height={VIEWBOX_HEIGHT} fill="url(#parcel-map-grid)" className="text-muted-foreground" />
          <circle
            cx={centerPoint.x}
            cy={centerPoint.y}
            r={Math.max((radiusMiles ?? extentMiles) * ((VIEWBOX_WIDTH - VIEWBOX_PADDING * 2) / (extentMiles * 2 || 1)), 12)}
            fill="none"
            stroke="currentColor"
            strokeDasharray="4 4"
            className="text-border"
          />
          {pointBoundaryPaths.map((entry) => (
            <path
              key={entry.id}
              d={entry.path}
              fill={entry.fill}
              stroke={entry.stroke}
              strokeWidth="1.5"
            />
          ))}
          {primaryBoundaryPaths.map((path, index) => (
            <path
              key={`primary-${index}-${path.slice(0, 12)}`}
              d={path}
              fill="rgba(34, 197, 94, 0.12)"
              stroke="rgba(34, 197, 94, 0.75)"
              strokeWidth="2"
            />
          ))}
          <line x1={0} x2={VIEWBOX_WIDTH} y1={centerPoint.y} y2={centerPoint.y} stroke="currentColor" strokeOpacity="0.08" />
          <line x1={centerPoint.x} x2={centerPoint.x} y1={0} y2={VIEWBOX_HEIGHT} stroke="currentColor" strokeOpacity="0.08" />
          {projectedPoints.map((point) => {
            const svgPoint = toSvgPoint(point.projected, extentMiles);
            const tone = point.tone ?? 'candidate';
            return (
              <g key={point.id}>
                <circle
                  cx={svgPoint.x}
                  cy={svgPoint.y}
                  r={point.tone === 'anchor' ? 8 : 6}
                  className={tone === 'anchor' ? 'fill-primary' : tone === 'highlight' ? 'fill-emerald-600' : 'fill-foreground'}
                  opacity={point.tone === 'anchor' ? 1 : 0.9}
                />
                <title>{point.label}</title>
              </g>
            );
          })}
          <g>
            <circle cx={centerPoint.x} cy={centerPoint.y} r="9" className="fill-background stroke-primary" strokeWidth="3" />
            <circle cx={centerPoint.x} cy={centerPoint.y} r="3.5" className="fill-primary" />
            <title>{center.label}</title>
          </g>
        </svg>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1">
          <MapPinned className="h-3.5 w-3.5" />
          {center.label}
        </span>
        {center.subtitle && (
          <span className="inline-flex items-center rounded-md border bg-background px-2 py-1">
            {center.subtitle}
          </span>
        )}
        {points.slice(0, 4).map((point) => (
          <span
            key={point.id}
            className={cn('inline-flex flex-col items-start gap-0.5 rounded-md border px-2 py-1', toneClasses(point.tone))}
          >
            <span className="inline-flex items-center gap-1">
              {point.label}
              {point.distanceMiles != null && <span className="opacity-70">{point.distanceMiles.toFixed(2)} mi</span>}
            </span>
            {point.subtitle && <span className="text-[10px] opacity-70">{point.subtitle}</span>}
          </span>
        ))}
        {points.length === 0 && !hasBoundary && (
          <span className="inline-flex items-center rounded-md border bg-background px-2 py-1">
            {emptyLabel}
          </span>
        )}
      </div>
    </div>
  );
}
