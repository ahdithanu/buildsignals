import { z } from 'zod';
import type { GeographicPoint } from '@/components/GeographicMap';

// Configure before object construction: a caught eval probe still violates CSP.
z.config({ jitless: true });

export const UNKNOWN_GEOGRAPHY = '__unknown__';
export const COVERAGE_PAGE_SIZE = 100;
export const RECORD_PAGE_SIZE = 50;
export type CoverageKind = 'all' | 'permit' | 'planning' | 'parcel';

const count = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER);
const text = z.string().max(10_000);
const identity = z.string().min(1).max(512);
const stateCode = z.enum(['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
  'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND',
  'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', UNKNOWN_GEOGRAPHY]);
const latitude = z.number().finite().min(-85).max(85).nullable();
const longitude = z.number().finite().min(-180).max(180).nullable();
const counts = { permit_count: count, planning_count: count, parcel_count: count, mapped_count: count, unmapped_count: count };
type Counts = { [Key in keyof typeof counts]: number };
const consistentCounts = (value: Counts) => Number.isSafeInteger(value.permit_count + value.planning_count + value.parcel_count)
  && value.permit_count + value.planning_count + value.parcel_count === value.mapped_count + value.unmapped_count;
const coordinatePair = (value: { latitude?: number | null; longitude?: number | null }) => value.latitude !== undefined
  && value.longitude !== undefined && (value.latitude === null) === (value.longitude === null);
const geography = { ...counts, state: stateCode, label: text, latitude, longitude };
const stateSchema = z.object(geography).strict().refine(consistentCounts).refine(coordinatePair);
const groupSchema = z.object({ ...geography, id: identity, jurisdiction: text.nullable() }).strict().refine(consistentCounts).refine(coordinatePair);
const pagination = { limit: z.number().int().min(1).max(100), offset: z.number().int().min(0).max(100_000),
  next_offset: z.number().int().min(0).max(100_000).nullable(), previous_offset: z.number().int().min(0).max(100_000).nullable() };
const orderedOffsets = (value: { offset: number; next_offset?: number | null; previous_offset?: number | null }) =>
  (value.next_offset === null || value.next_offset > value.offset) && (value.previous_offset === null || value.previous_offset < value.offset);

export const coverageSchema = z.object({
  measured_at: z.string().datetime({ offset: true }), totals: z.object(counts).strict().refine(consistentCounts),
  states: z.array(stateSchema).max(52), groups: z.array(groupSchema).max(100), grouping: z.enum(['state', 'jurisdiction']),
  total_groups: count, ...pagination, truncated: z.boolean(),
}).strict().refine(orderedOffsets).refine(value => value.groups.length <= value.limit
  && value.groups.length <= value.total_groups
  && new Set(value.groups.map(group => group.id)).size === value.groups.length
  && new Set(value.states.map(state => state.state)).size === value.states.length);

const recordSchema = z.object({
  id: identity, kind: z.enum(['permit', 'planning', 'parcel']), title: text,
  address: text.nullable(), city: text.nullable(), state: stateCode, jurisdiction: text.min(1),
  latitude, longitude, location_method: z.enum(['source_coordinate', 'census_address_range_estimate']).nullable(),
}).strict().refine(coordinatePair);
export const recordsSchema = z.object({ items: z.array(recordSchema).max(100), total: count, ...pagination })
  .strict().refine(orderedOffsets).refine(value => value.items.length <= value.limit && value.items.length <= value.total
    && new Set(value.items.map(item => `${item.kind}:${item.id}`)).size === value.items.length);

export type CoverageResponse = z.infer<typeof coverageSchema>;
export type CoverageGroup = CoverageResponse['groups'][number];
export type CoverageRecord = z.infer<typeof recordSchema>;
export function inventoryCount(value: Counts) { return value.permit_count + value.planning_count + value.parcel_count; }
export function normalizedCoverageState(value: string) {
  return value === UNKNOWN_GEOGRAPHY ? value : /^[A-Z]{2}$/.test(value.trim().toUpperCase()) ? value.trim().toUpperCase() : '';
}
export function geographyLabel(group: CoverageGroup, grouping: CoverageResponse['grouping']) {
  return grouping === 'state' && group.state === UNKNOWN_GEOGRAPHY ? 'Unknown state'
    : grouping === 'jurisdiction' && (!group.jurisdiction?.trim() || group.jurisdiction === UNKNOWN_GEOGRAPHY)
      ? 'Jurisdiction not supplied' : group.label;
}
export function coveragePoints(groups: CoverageGroup[], grouping: CoverageResponse['grouping'] = 'state'): (GeographicPoint & { count: number })[] {
  return groups.filter(group => group.latitude !== null && group.longitude !== null && Math.abs(group.latitude) <= 85)
    .map(group => ({ id: `coverage:${group.id}`, kind: 'heat', latitude: group.latitude!, longitude: group.longitude!,
      title: `Aggregate geography: ${geographyLabel(group, grouping)}; ${group.mapped_count.toLocaleString()} mapped, ${group.unmapped_count.toLocaleString()} unmapped records. Not a parcel center.`,
      count: group.mapped_count, weight: 12 + Math.log2(Math.max(1, group.mapped_count)),
    }));
}
export function coverageRecordHref(record: CoverageRecord) {
  const id = encodeURIComponent(record.id);
  return record.kind === 'planning' ? `/planning?record_id=${id}` : record.kind === 'parcel' ? `/parcels/${id}` : `/permits/${id}`;
}
