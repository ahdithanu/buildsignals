import type { ParcelAvailabilityImportRow } from '@/types/parcel';

const REQUIRED_HEADERS = ['source_id', 'external_parcel_id', 'status', 'evidence_type', 'confidence'];
const MAX_ROWS = 500;

export interface ParsedParcelAvailabilityCsv {
  rows: ParcelAvailabilityImportRow[];
  errors: Array<{ row: number; reason: string }>;
}

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let value = '';
  let quoted = false;

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"') {
      if (quoted && line[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === ',' && !quoted) {
      values.push(value.trim());
      value = '';
    } else {
      value += character;
    }
  }
  values.push(value.trim());
  return values;
}

function normalizeHeader(header: string) {
  return header.trim().toLowerCase().replace(/\s+/g, '_');
}

function optionalValue(value: string | undefined) {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}

function optionalNumber(value: string | undefined) {
  const normalized = optionalValue(value);
  if (!normalized) return undefined;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

export function parseParcelAvailabilityCsv(input: string): ParsedParcelAvailabilityCsv {
  const lines = input.replace(/^\uFEFF/, '').split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length === 0) return { rows: [], errors: [{ row: 1, reason: 'CSV is empty' }] };

  const headers = parseCsvLine(lines[0]).map(normalizeHeader);
  const positions = new Map(headers.map((header, index) => [header, index]));
  const missing = REQUIRED_HEADERS.filter((header) => !positions.has(header));
  if (missing.length > 0) {
    return { rows: [], errors: [{ row: 1, reason: `Missing required columns: ${missing.join(', ')}` }] };
  }

  const rows: ParcelAvailabilityImportRow[] = [];
  const errors: Array<{ row: number; reason: string }> = [];
  for (const [lineIndex, line] of lines.slice(1, MAX_ROWS + 1).entries()) {
    const rowNumber = lineIndex + 2;
    const values = parseCsvLine(line);
    const get = (header: string) => values[positions.get(header) ?? -1]?.trim() ?? '';
    const sourceId = get('source_id');
    const externalParcelId = get('external_parcel_id');
    const status = get('status').toLowerCase();
    const evidenceType = get('evidence_type').toLowerCase();
    const confidence = Number(get('confidence'));
    if (!sourceId || !externalParcelId) {
      errors.push({ row: rowNumber, reason: 'source_id and external_parcel_id are required' });
      continue;
    }
    if (!['available', 'for_sale', 'listed', 'broker_listed', 'owner_indicated_available'].includes(status)) {
      errors.push({ row: rowNumber, reason: 'status must be an explicit availability status' });
      continue;
    }
    if (!['listing', 'broker', 'owner', 'auction'].includes(evidenceType)) {
      errors.push({ row: rowNumber, reason: 'evidence_type must be listing, broker, owner, or auction' });
      continue;
    }
    if (!Number.isFinite(confidence) || confidence < 0.7 || confidence > 1) {
      errors.push({ row: rowNumber, reason: 'confidence must be a number between 0.7 and 1.0' });
      continue;
    }
    const askingPrice = optionalNumber(get('asking_price'));
    if (askingPrice === null) {
      errors.push({ row: rowNumber, reason: 'asking_price must be a non-negative number when provided' });
      continue;
    }
    if (!optionalValue(get('source_url')) && !optionalValue(get('excerpt'))) {
      errors.push({ row: rowNumber, reason: 'source_url or excerpt is required for evidence' });
      continue;
    }
    rows.push({
      source_id: sourceId,
      external_parcel_id: externalParcelId,
      status: status as ParcelAvailabilityImportRow['status'],
      evidence_type: evidenceType as ParcelAvailabilityImportRow['evidence_type'],
      confidence,
      source_url: optionalValue(get('source_url')),
      excerpt: optionalValue(get('excerpt')),
      observed_at: optionalValue(get('observed_at')),
      asking_price: askingPrice,
      contact_name: optionalValue(get('contact_name')),
      contact_company: optionalValue(get('contact_company')),
    });
  }

  if (lines.length - 1 > MAX_ROWS) {
    errors.push({ row: MAX_ROWS + 2, reason: `Only the first ${MAX_ROWS} data rows are accepted` });
  }
  return { rows, errors };
}

export const PARCEL_AVAILABILITY_CSV_TEMPLATE = [
  'source_id,external_parcel_id,status,evidence_type,confidence,source_url,excerpt,observed_at,asking_price,contact_name,contact_company',
  'parcel-source-id,parcel-123,listed,broker,0.85,https://example.com/listing,"Public listing excerpt",2026-10-21T12:00:00Z,2250000,,Example Brokerage',
].join('\n');
