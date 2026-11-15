import { z } from 'zod';

const label = z.string().min(1).max(255);
const timestamp = z.string().datetime({ offset: true });

export const parcelUseContextSchema = z.object({
  parcel_id: z.string(),
  as_of: timestamp,
  method_version: z.literal('parcel-use-context-v1'),
  jurisdiction: z.string().nullable(),
  state: z.string().nullable(),
  status: z.enum(['missing', 'reported', 'conflicting', 'incomplete']),
  recorded_zoning_code: label.nullable(),
  reported_zoning_codes: z.array(label).max(50),
  recorded_land_uses: z.array(label).max(51),
  evidence: z.array(z.object({
    fact_id: z.string(),
    kind: z.enum(['zoning', 'land_use']),
    recorded_value: label,
    source_url: z.string().nullable(),
    confidence: z.number().finite().min(0).max(1),
    observed_at: timestamp,
    last_verified_at: timestamp,
  })).max(50),
  gaps: z.array(z.string()).max(20),
  potential_uses: z.array(z.string()).length(0),
  potential_uses_status: z.literal('not_assessed'),
  ai_used: z.literal(false),
});

export type ParcelUseContextResponse = z.infer<typeof parcelUseContextSchema>;
