import { describe, expect, it } from 'vitest';
import { mapDeal } from '@/api/deals';
import { formatCurrency } from '@/lib/formatters';

describe('recorded property facts', () => {
  it.each([null, undefined, NaN, Infinity, -Infinity, '', '0', false, {}])('keeps missing or malformed facts unknown: %j', value => {
    const deal = mapDeal({ asking_price: value, year_built: value, sq_ft: value, units: value });
    expect([deal.askingPrice, deal.yearBuilt, deal.squareFeet, deal.units]).toEqual([null, null, null, null]);
  });

  it.each([0, 25_000])('preserves recorded finite values, including genuine zero: %s', value => {
    const deal = mapDeal({ asking_price: value, year_built: value, sq_ft: value, units: value });
    expect([deal.askingPrice, deal.yearBuilt, deal.squareFeet, deal.units]).toEqual([value, value, value, value]);
  });

  it.each([null, undefined, '', 'not-a-risk'])('does not invent medium risk for %j', risk_level => {
    expect(mapDeal({ risk_level }).riskLevel).toBeNull();
  });

  it.each(['low', 'medium', 'high'])('preserves a recorded risk level: %s', risk_level => {
    expect(mapDeal({ risk_level }).riskLevel).toBe(risk_level);
  });

  it.each([null, undefined, NaN, Infinity, -Infinity])('formats unavailable price as Unknown: %s', value => {
    expect(formatCurrency(value)).toBe('Unknown');
  });

  it('keeps genuine zero price distinct from missing price', () => {
    expect(formatCurrency(0)).toBe('$0');
  });
});

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
