import { expect, it, vi } from 'vitest';

it('constructs and parses parcel context without attempting dynamic code generation', async () => {
  vi.resetModules();
  const { z } = await import('zod');
  const previous = z.config().jitless;
  z.config({ jitless: false });
  const dynamicCode = vi.spyOn(globalThis, 'Function').mockImplementation(function () {
    throw new EvalError('Synthetic strict CSP blocks dynamic code');
  });
  try {
    const { parcelUseContextSchema } = await import('@/types/parcelUseContext');
    const result = parcelUseContextSchema.parse({
      parcel_id: 'synthetic', as_of: '2026-11-15T12:00:00Z', method_version: 'parcel-use-context-v1',
      jurisdiction: null, state: null, status: 'missing', recorded_zoning_code: null,
      reported_zoning_codes: [], recorded_land_uses: [], evidence: [], gaps: [],
      potential_uses: [], potential_uses_status: 'not_assessed', ai_used: false,
    });
    expect(result.potential_uses_status).toBe('not_assessed');
    expect(dynamicCode).not.toHaveBeenCalled();
  } finally {
    dynamicCode.mockRestore();
    z.config({ jitless: previous });
    vi.resetModules();
  }
});
