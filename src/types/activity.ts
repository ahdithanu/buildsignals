import type { ActivityType, SignalType, SignalConfidence, SignalImpact } from './common';

export interface Activity {
  id: string;
  type: ActivityType;
  content: string;
  user: string;
  date: string;
}

export interface CreateActivityRequest {
  type: ActivityType;
  content: string;
  user?: string;
}

export interface Signal {
  id: string;
  type: SignalType;
  property: string;
  summary: string;
  confidence: SignalConfidence;
  date: string;
  impact: SignalImpact;
}

export interface CreateSignalRequest {
  type: SignalType;
  property: string;
  summary: string;
  confidence: SignalConfidence;
  impact: SignalImpact;
}

export interface DealDocument {
  name: string;
  type: string;
  date: string;
}
