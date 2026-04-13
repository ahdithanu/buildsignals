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

export function getRiskColor(risk: string): string {
  switch (risk) {
    case 'low': return 'bg-success/10 text-success';
    case 'medium': return 'bg-warning/10 text-warning';
    case 'high': return 'bg-destructive/10 text-destructive';
    default: return 'bg-muted text-muted-foreground';
  }
}

export function getStatusColor(status: string): string {
  switch (status) {
    case 'new': return 'bg-info/10 text-info';
    case 'qualified': return 'bg-accent/15 text-accent-foreground';
    case 'underwriting': return 'bg-warning/10 text-warning';
    case 'ic-review':
    case 'ic_review': return 'bg-purple-100 text-purple-700';
    case 'loi-sent':
    case 'loi_sent': return 'bg-success/10 text-success';
    case 'psa': return 'bg-emerald-100 text-emerald-700';
    case 'closing': return 'bg-success/15 text-success';
    case 'closed': return 'bg-success/20 text-success';
    case 'dead': return 'bg-muted text-muted-foreground';
    default: return 'bg-muted text-muted-foreground';
  }
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
