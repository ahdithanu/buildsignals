import { z } from 'zod';
import { coverageSchema, UNKNOWN_GEOGRAPHY } from '@/lib/mapCoverage';

z.config({ jitless: true });
const count = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER);
const latitude = z.number().finite().min(-85).max(85);
const longitude = z.number().finite().min(-180).max(180);
const cell = z.object({
  id: z.string().min(1).max(128), latitude, longitude, count: count.positive(),
  source_coordinate_count: count, estimated_count: count,
  south: latitude, north: latitude, west: longitude, east: longitude,
}).strict().refine(value => value.count === value.source_coordinate_count + value.estimated_count
  && value.south < value.north && value.west < value.east
  && value.latitude >= value.south && value.latitude <= value.north
  && value.longitude >= value.west && value.longitude <= value.east);

export const permitDensitySchema = z.object({
  measured_at: z.string().datetime({ offset: true }), state: z.string().nullable(),
  total_permits: count, mapped_permits: count, unmapped_permits: count,
  source_coordinate_count: count, estimated_count: count,
  cell_degrees: z.number().finite().positive().max(8), cells: z.array(cell).max(2048), complete: z.literal(true),
}).strict().refine(value => value.total_permits === value.mapped_permits + value.unmapped_permits
  && value.mapped_permits === value.source_coordinate_count + value.estimated_count
  && value.cells.reduce((sum, item) => sum + item.count, 0) === value.mapped_permits
  && value.cells.reduce((sum, item) => sum + item.source_coordinate_count, 0) === value.source_coordinate_count
  && value.cells.reduce((sum, item) => sum + item.estimated_count, 0) === value.estimated_count
  && new Set(value.cells.map(item => item.id)).size === value.cells.length);

export const permitCoverageSchema = coverageSchema.refine(value => value.grouping === 'state'
  && value.offset === 0 && value.next_offset === null && !value.truncated
  && value.groups.length === value.total_groups
  && value.totals.planning_count === 0 && value.totals.parcel_count === 0
  && value.groups.every(group => group.planning_count === 0 && group.parcel_count === 0)
  && value.groups.reduce((sum, group) => sum + group.permit_count, 0) === value.totals.permit_count
  && value.groups.reduce((sum, group) => sum + group.mapped_count, 0) === value.totals.mapped_count
  && value.groups.reduce((sum, group) => sum + group.unmapped_count, 0) === value.totals.unmapped_count);

export type PermitDensity = z.infer<typeof permitDensitySchema>;
export const mapViews = ['activity', 'coverage', 'filings'] as const;
export type MapView = typeof mapViews[number];
export function mapView(params: URLSearchParams): MapView {
  return params.get('view') === 'filings' ? 'filings' : params.get('view') === 'coverage' ? 'coverage' : 'activity';
}
export function mapFilterParams(params: URLSearchParams, changes: { state?: string; zip3?: string; view?: MapView }) {
  const next = new URLSearchParams(params);
  if (changes.view !== undefined) {
    if (changes.view === 'activity') next.delete('view'); else next.set('view', changes.view);
  }
  if (changes.state !== undefined) {
    if (changes.state) next.set('state', changes.state); else next.delete('state');
    next.delete('zip3');
  }
  if (changes.zip3 !== undefined) {
    if (/^\d{3}$/.test(changes.zip3)) next.set('zip3', changes.zip3); else next.delete('zip3');
  }
  return next;
}
export function permitStateLabel(state: string, states: { state: string; label: string }[]) {
  return state === UNKNOWN_GEOGRAPHY ? 'Unknown state' : states.find(item => item.state === state)?.label || state;
}
