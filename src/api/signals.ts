import { apiClient } from './client';
import type { Signal, CreateSignalRequest } from '@/types/activity';
import type { SignalConfidence, SignalImpact } from '@/types/common';

/* eslint-disable @typescript-eslint/no-explicit-any */
export function mapSignal(raw: any): Signal {
  const severity = raw.severity || 0;
  let confidence: SignalConfidence = 'low';
  if (severity > 7) confidence = 'high';
  else if (severity > 4) confidence = 'medium';

  let impact: SignalImpact = 'positive';
  if (severity > 6) impact = 'negative';
  else if (severity > 3) impact = 'neutral';

  return {
    id: raw.id,
    type: raw.signal_type || '',
    property: raw.deal_name || 'Unknown',
    summary: raw.description || '',
    confidence,
    date: raw.created_at || '',
    impact,
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export const signalsApi = {
  list: async (): Promise<Signal[]> => {
    const rawList = await apiClient.get<any[]>('/signals');
    return rawList.map(mapSignal);
  },

  create: async (data: CreateSignalRequest): Promise<Signal> => {
    const body = {
      signal_type: data.type,
      description: data.summary,
      source: data.property,
    };
    const raw = await apiClient.post<any>('/signals', body);
    return mapSignal(raw);
  },

  listForDeal: async (dealId: string): Promise<Signal[]> => {
    const rawList = await apiClient.get<any[]>(`/deals/${dealId}/signals`);
    return rawList.map(mapSignal);
  },
};
