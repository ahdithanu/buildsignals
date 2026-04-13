import { apiClient } from './client';
import type { Activity, CreateActivityRequest } from '@/types/activity';

/* eslint-disable @typescript-eslint/no-explicit-any */
function mapActivity(raw: any): Activity {
  const subject = raw.subject || '';
  const body = raw.body || '';
  const content = [subject, body].filter(Boolean).join(' - ');

  return {
    id: raw.id,
    type: raw.activity_type || 'note',
    content: content || '',
    user: 'System',
    date: raw.created_at || '',
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export const activitiesApi = {
  list: async (dealId: string): Promise<Activity[]> => {
    const rawList = await apiClient.get<any[]>(`/deals/${dealId}/activities`);
    return rawList.map(mapActivity);
  },

  create: async (dealId: string, data: CreateActivityRequest): Promise<Activity> => {
    const body = {
      activity_type: data.type,
      subject: data.content,
      body: '',
    };
    const raw = await apiClient.post<any>(`/deals/${dealId}/activities`, body);
    return mapActivity(raw);
  },
};
