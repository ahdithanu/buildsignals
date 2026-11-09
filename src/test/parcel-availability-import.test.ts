import { describe, expect, it } from 'vitest';
import {
  PARCEL_AVAILABILITY_CSV_TEMPLATE,
  parseParcelAvailabilityCsv,
} from '@/lib/parcelAvailabilityImport';

describe('parcel availability CSV intake', () => {
  it('parses the bounded evidence contract and quoted excerpts', () => {
    const parsed = parseParcelAvailabilityCsv(PARCEL_AVAILABILITY_CSV_TEMPLATE);

    expect(parsed.errors).toEqual([]);
    expect(parsed.rows).toEqual([expect.objectContaining({
      source_id: 'parcel-source-id',
      external_parcel_id: 'parcel-123',
      status: 'listed',
      evidence_type: 'broker',
      confidence: 0.85,
      excerpt: 'Public listing excerpt',
      asking_price: 2250000,
    })]);
  });

  it('rejects missing identity and weak evidence rows before network submission', () => {
    const parsed = parseParcelAvailabilityCsv([
      'source_id,external_parcel_id,status,evidence_type,confidence',
      ',parcel-1,listed,broker,0.9',
      'source-1,parcel-2,listed,broker,0.69',
      'source-1,parcel-3,unknown,broker,0.9',
    ].join('\n'));

    expect(parsed.rows).toHaveLength(0);
    expect(parsed.errors).toHaveLength(3);
  });

  it('requires all identity and evidence headers', () => {
    const parsed = parseParcelAvailabilityCsv('source_id,external_parcel_id\nsource-1,parcel-1');

    expect(parsed.rows).toEqual([]);
    expect(parsed.errors[0]?.reason).toContain('Missing required columns');
  });

  it('requires source-backed evidence and validates optional price fields', () => {
    const parsed = parseParcelAvailabilityCsv([
      'source_id,external_parcel_id,status,evidence_type,confidence,asking_price',
      'source-1,parcel-1,listed,broker,0.9,,',
      'source-1,parcel-2,listed,broker,0.9,-1',
    ].join('\n'));

    expect(parsed.rows).toHaveLength(0);
    expect(parsed.errors.map((error) => error.reason)).toEqual([
      'source_url or excerpt is required for evidence',
      'asking_price must be a non-negative number when provided',
    ]);
  });
});
