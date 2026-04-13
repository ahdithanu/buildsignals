export type RiskLevel = 'low' | 'medium' | 'high';

export type DealStatus = 'new' | 'qualified' | 'underwriting' | 'ic-review' | 'loi-sent' | 'psa' | 'closing' | 'closed' | 'dead';

export type SignalType = string;

export type SignalConfidence = 'high' | 'medium' | 'low';

export type SignalImpact = 'positive' | 'negative' | 'neutral';

export type ActivityType = 'call' | 'email' | 'sms' | 'note' | 'meeting' | 'system';

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ApiError {
  detail: string;
  status: number;
}
