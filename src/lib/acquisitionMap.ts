import type { AcquisitionCaseStatus, AcquisitionRadarItem, ParcelFact } from '@/types/parcel';

export interface AcquisitionMapSignal {
  id: string;
  name: string;
  stage: 'pre_approval' | 'approved';
  score: number;
  market: string;
  latestSignalAt: string;
  searchId: string;
}

const recordValue = (fact: ParcelFact) =>
  fact.value && typeof fact.value === 'object' && !Array.isArray(fact.value)
    ? fact.value as Record<string, unknown>
    : {};

function textValue(fact: ParcelFact, keys: string[]) {
  const value = recordValue(fact);
  for (const key of keys) {
    const candidate = value[key];
    if (typeof candidate === 'string' && candidate.trim()) return candidate.trim();
    if (typeof candidate === 'number') return String(candidate);
  }
  return typeof fact.value === 'string' && fact.value.trim() ? fact.value.trim() : null;
}

export function radarSignals(items: AcquisitionRadarItem[]): AcquisitionMapSignal[] {
  const byDeal = new Map<string, AcquisitionMapSignal>();
  for (const item of items) {
    for (const signal of item.signals) {
      const existing = byDeal.get(signal.deal_id);
      const candidate: AcquisitionMapSignal = {
        id: signal.deal_id,
        name: signal.deal_name,
        stage: signal.approval_stage === 'approved' ? 'approved' : 'pre_approval',
        score: Math.round(item.radar_score),
        market: [item.parcel.city, item.parcel.state].filter(Boolean).join(', ') || 'Market pending',
        latestSignalAt: signal.created_at,
        searchId: signal.search_id,
      };
      if (!existing || candidate.score > existing.score) byDeal.set(signal.deal_id, candidate);
    }
  }
  return [...byDeal.values()].sort((left, right) => right.score - left.score);
}

export function ownerName(facts: ParcelFact[]) {
  const ownership = facts.find((fact) => fact.fact_type === 'ownership');
  return ownership
    ? textValue(ownership, ['owner_name', 'owner', 'name', 'taxpayer_name', 'grantee'])
    : null;
}

export function lastSale(facts: ParcelFact[]) {
  const sale = facts.find((fact) => ['last_sale', 'sale'].includes(fact.fact_type));
  if (!sale) return null;
  const date = textValue(sale, ['last_sale_date', 'sale_date', 'date', 'recorded_at']);
  const price = textValue(sale, ['last_sale_price', 'sale_price', 'price', 'amount']);
  return { date, price, fact: sale };
}

export function ownershipTenureYears(item: AcquisitionRadarItem) {
  const sale = lastSale(item.facts ?? []);
  if (!sale?.date) return null;
  const saleDate = new Date(sale.date);
  const verified = new Date(item.parcel.last_verified_at);
  if (Number.isNaN(saleDate.getTime()) || Number.isNaN(verified.getTime())) return null;
  return Math.max(0, (verified.getTime() - saleDate.getTime()) / 31_557_600_000);
}

export function hasTaxEvidence(facts: ParcelFact[]) {
  return facts.some((fact) => /tax|delinquen|lien/.test(fact.fact_type.toLowerCase()));
}

export function workflowLabel(status: AcquisitionCaseStatus) {
  const labels: Record<AcquisitionCaseStatus, string> = {
    candidate: 'Candidate',
    shortlisted: 'Shortlisted',
    contacted: 'Contacted',
    dismissed: 'Dismissed',
    promoted: 'Promoted',
  };
  return labels[status];
}

export function sourceLabel(facts: ParcelFact[]) {
  const withSource = facts.find((fact) => fact.source_url);
  const factCount = `${facts.length} ${facts.length === 1 ? 'fact' : 'facts'}`;
  if (!withSource?.source_url) return facts.length ? `${factCount} verified` : 'No parcel facts yet';
  try {
    return `${new URL(withSource.source_url).hostname.replace(/^www\./, '')} · ${factCount}`;
  } catch {
    return `${factCount} verified`;
  }
}
