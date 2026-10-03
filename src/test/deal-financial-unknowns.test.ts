import { describe, expect, it } from 'vitest';
import { mapDeal } from '@/api/deals';

describe('recorded underwriting outputs', () => {
  it.each([undefined, null, {}])('keeps missing outputs unknown: %j', outputs => {
    const deal = mapDeal({ id: 'd', outputs });
    expect([deal.noi, deal.projectedIrr, deal.equityMultiple, deal.cashOnCash]).toEqual([null, null, null, null]);
  });

  it('preserves genuine zeros', () => {
    const deal = mapDeal({ outputs: { noi: 0, irr: 0, equity_multiple: 0, cash_on_cash: 0 } });
    expect([deal.noi, deal.projectedIrr, deal.equityMultiple, deal.cashOnCash]).toEqual([0, 0, 0, 0]);
  });

  it('preserves negative results and percentage units', () => {
    const deal = mapDeal({ outputs: { noi: -5000, irr: -0.05, equity_multiple: 0.8, cash_on_cash: 0.125 } });
    expect([deal.noi, deal.projectedIrr, deal.equityMultiple, deal.cashOnCash]).toEqual([-5000, -5, 0.8, 12.5]);
  });

  it.each([null, undefined, NaN, Infinity, -Infinity, '', '0', false, {}])('does not coerce malformed outputs: %j', value => {
    const deal = mapDeal({ outputs: { noi: value, irr: value, equity_multiple: value, cash_on_cash: value } });
    expect([deal.noi, deal.projectedIrr, deal.equityMultiple, deal.cashOnCash]).toEqual([null, null, null, null]);
  });

  it('rejects percentage overflow without discarding other finite metrics', () => {
    const deal = mapDeal({ outputs: { noi: 100, irr: Number.MAX_VALUE } });
    expect(deal.projectedIrr).toBeNull();
    expect(deal.noi).toBe(100);
  });
});
