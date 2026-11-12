import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/api/client';
import { mapDeal } from '@/api/deals';
import DealInbox from '@/pages/DealInbox';
import type { Deal } from '@/types/deal';

const workspace = vi.hoisted(() => ({
  deals: [] as Deal[], create: vi.fn(), refetch: vi.fn(),
}));
vi.mock('@/components/Layout', () => ({
  Layout: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
vi.mock('@/hooks/useDeals', () => ({
  useDeals: () => ({ data: workspace.deals, isLoading: false, error: null, refetch: workspace.refetch }),
  useCreateDeal: () => ({ mutate: workspace.create, isPending: false }),
}));

type PreviewFinancials = Pick<Deal, 'noi' | 'projectedIrr' | 'equityMultiple'>;
const name = 'SYNTHETIC preview financials';

function openPreview(values: Partial<PreviewFinancials>) {
  workspace.deals = [{
    ...mapDeal({
      id: 'preview-deal', name, city: 'Austin', state: 'TX', property_type: 'Retail',
      status: 'new', asking_price: 250_000,
      outputs: { noi: 12_345, irr: 0.075, equity_multiple: 1.5 },
    }),
    ...values,
  }];
  render(<MemoryRouter><DealInbox /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', {
    name: `Deal ${name} \u2014 press Enter to preview`,
  }));
  expect(screen.getByRole('heading', { name })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open Deal' })).toBeInTheDocument();
}

function expectMetric(label: string, value: string) {
  const metric = screen.getByText(label, { exact: true }).parentElement!;
  expect(within(metric).getByText(value, { exact: true })).toBeInTheDocument();
}

beforeEach(() => {
  vi.resetAllMocks();
  workspace.deals = [];
});

afterEach(() => {
  for (const method of ['get', 'post', 'patch', 'put', 'delete'] as const) {
    expect(apiClient[method]).not.toHaveBeenCalled();
  }
  expect(workspace.create).not.toHaveBeenCalled();
});

describe('Deal Inbox preview financial outputs', () => {
  it.each([
    { case: 'missing NOI', values: { noi: null }, labels: ['NOI'] },
    { case: 'missing IRR', values: { projectedIrr: null }, labels: ['Projected IRR'] },
    { case: 'missing equity multiple', values: { equityMultiple: null }, labels: ['Equity Multiple'] },
    {
      case: 'all outputs missing',
      values: { noi: null, projectedIrr: null, equityMultiple: null },
      labels: ['NOI', 'Projected IRR', 'Equity Multiple'],
    },
  ])('renders Not calculated for $case without breaking the preview', ({ values, labels }) => {
    openPreview(values);
    for (const label of labels) expectMetric(label, 'Not calculated');
    const financialGrid = within(screen.getByText('NOI', { exact: true }).parentElement!.parentElement!);
    expect(financialGrid.getAllByText('Not calculated', { exact: true })).toHaveLength(labels.length);
    expect(screen.queryByText('%', { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText('x', { exact: true })).not.toBeInTheDocument();
  });

  it.each([
    { case: 'zero', values: { noi: 0, projectedIrr: 0, equityMultiple: 0 }, noi: '$0', irr: '0%', equity: '0x' },
    {
      case: 'negative', values: { noi: -12_345, projectedIrr: -7.5, equityMultiple: -0.5 },
      noi: '$-12,345', irr: '-7.5%', equity: '-0.5x',
    },
  ])('preserves calculated $case values instead of treating them as missing', ({ values, noi, irr, equity }) => {
    openPreview(values);
    expectMetric('NOI', noi);
    expectMetric('Projected IRR', irr);
    expectMetric('Equity Multiple', equity);
    expect(screen.queryByText('Not calculated', { exact: true })).not.toBeInTheDocument();
  });
});
