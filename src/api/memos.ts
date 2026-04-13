import { apiClient } from './client';
import type { Memo, UpdateMemoRequest } from '@/types/memo';

/* eslint-disable @typescript-eslint/no-explicit-any */

/** Parse markdown content into memo sections by looking for ## headings */
export function mapMemo(raw: any): Memo {
  if (!raw) {
    return {
      executiveSummary: '',
      whyThisDeal: '',
      propertyOverview: '',
      marketOverview: '',
      financialSummary: '',
      risksAndMitigants: '',
      valueCreationPlan: '',
      recommendedAction: '',
    };
  }

  // If the raw object already has section keys (frontend shape), pass through
  if (raw.executiveSummary !== undefined) {
    return raw as Memo;
  }

  const content = raw.content || '';
  if (!content) {
    return {
      executiveSummary: '',
      whyThisDeal: '',
      propertyOverview: '',
      marketOverview: '',
      financialSummary: '',
      risksAndMitigants: '',
      valueCreationPlan: '',
      recommendedAction: '',
    };
  }

  // Parse markdown sections
  const sections = parseMemoMarkdown(content);

  return {
    executiveSummary: sections['executive summary'] || sections['summary'] || content,
    whyThisDeal: sections['why this deal'] || sections['investment thesis'] || '',
    propertyOverview: sections['property overview'] || sections['property'] || '',
    marketOverview: sections['market overview'] || sections['market'] || sections['market analysis'] || '',
    financialSummary: sections['financial summary'] || sections['financials'] || sections['financial analysis'] || '',
    risksAndMitigants: sections['risks and mitigants'] || sections['risks'] || sections['risk analysis'] || '',
    valueCreationPlan: sections['value creation plan'] || sections['value creation'] || sections['value-add strategy'] || '',
    recommendedAction: sections['recommended action'] || sections['recommendation'] || sections['next steps'] || '',
  };
}

/** Parse markdown by ## headings into a map of lowercase heading -> content */
function parseMemoMarkdown(markdown: string): Record<string, string> {
  const sections: Record<string, string> = {};
  // Split on ## headings (with optional numbering like "## 1. Executive Summary")
  const parts = markdown.split(/^##\s+/m);

  for (const part of parts) {
    if (!part.trim()) continue;
    const newlineIndex = part.indexOf('\n');
    if (newlineIndex === -1) continue;
    // Strip leading numbers like "1. " from heading
    const heading = part.slice(0, newlineIndex).replace(/^\d+\.\s*/, '').trim().toLowerCase();
    const body = part.slice(newlineIndex + 1).trim();
    if (heading) {
      sections[heading] = body;
    }
  }

  return sections;
}

/** Convert frontend memo sections to backend update body */
function unmapMemoUpdate(data: UpdateMemoRequest): Record<string, string> {
  // Backend expects { title?, content? } so we assemble markdown from sections
  const parts: string[] = [];
  if (data.executiveSummary !== undefined) parts.push(`## 1. Executive Summary\n${data.executiveSummary}`);
  if (data.whyThisDeal !== undefined) parts.push(`## 2. Why This Deal\n${data.whyThisDeal}`);
  if (data.propertyOverview !== undefined) parts.push(`## 3. Property Overview\n${data.propertyOverview}`);
  if (data.marketOverview !== undefined) parts.push(`## 4. Market Overview\n${data.marketOverview}`);
  if (data.financialSummary !== undefined) parts.push(`## 5. Financial Summary\n${data.financialSummary}`);
  if (data.risksAndMitigants !== undefined) parts.push(`## 6. Risks and Mitigants\n${data.risksAndMitigants}`);
  if (data.valueCreationPlan !== undefined) parts.push(`## 7. Value Creation Plan\n${data.valueCreationPlan}`);
  if (data.recommendedAction !== undefined) parts.push(`## 8. Recommended Action\n${data.recommendedAction}`);

  return {
    content: parts.join('\n\n'),
  };
}

/* eslint-enable @typescript-eslint/no-explicit-any */

export const memosApi = {
  get: async (dealId: string): Promise<Memo> => {
    const raw = await apiClient.get<any>(`/deals/${dealId}/memo`);
    return mapMemo(raw);
  },

  generate: async (dealId: string): Promise<Memo> => {
    const raw = await apiClient.post<any>(`/deals/${dealId}/generate-memo`);
    return mapMemo(raw);
  },

  update: async (dealId: string, data: UpdateMemoRequest): Promise<Memo> => {
    const body = unmapMemoUpdate(data);
    const raw = await apiClient.put<any>(`/deals/${dealId}/memo`, body);
    return mapMemo(raw);
  },
};
