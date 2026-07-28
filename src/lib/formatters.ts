import type { DealStatus } from '@/types/common';

export function formatCurrency(value: number): string {
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`;
  return `$${value.toLocaleString()}`;
}

export function formatNumber(value: number): string {
  return value.toLocaleString();
}

export function getScoreColor(score: number): string {
  if (score >= 85) return 'text-success';
  if (score >= 70) return 'text-info';
  if (score >= 55) return 'text-warning';
  return 'text-destructive';
}

export function getScoreBg(score: number): string {
  if (score >= 85) return 'bg-success/10 text-success';
  if (score >= 70) return 'bg-info/10 text-info';
  if (score >= 55) return 'bg-warning/10 text-warning';
  return 'bg-destructive/10 text-destructive';
}


export const stageLabels: Record<DealStatus | string, string> = {
  'new': 'New',
  'qualified': 'Qualified',
  'underwriting': 'Underwriting',
  'ic-review': 'IC Review',
  'ic_review': 'IC Review',
  'loi-sent': 'LOI Sent',
  'loi_sent': 'LOI Sent',
  'psa': 'PSA',
  'closing': 'Closing',
  'closed': 'Closed',
  'dead': 'Dead',
};

export const pipelineStages: DealStatus[] = ['new', 'qualified', 'underwriting', 'ic-review', 'loi-sent', 'psa', 'closing', 'closed', 'dead'];
