import { apiClient } from './client';
import type { Contact, CreateContactRequest, UpdateContactRequest, FollowUp } from '@/types/contact';

/* eslint-disable @typescript-eslint/no-explicit-any */
function mapContact(raw: any): Contact {
  return {
    id: raw.id || '',
    dealId: raw.deal_id || '',
    name: raw.name || '',
    role: raw.role || '',
    company: raw.company || '',
    email: raw.email || '',
    phone: raw.phone || '',
    notes: raw.notes || '',
    lastContacted: raw.updated_at || raw.last_contacted || '',
  };
}

function mapFollowUp(raw: any): FollowUp {
  return {
    id: raw.id || '',
    contactId: raw.contact_id || '',
    contactName: raw.contact_name || '',
    dealName: raw.deal_name || '',
    dealId: raw.deal_id || '',
    dueDate: raw.due_date || raw.follow_up_date || '',
    note: raw.note || raw.notes || '',
    completed: raw.completed || false,
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export const contactsApi = {
  list: async (dealId: string): Promise<Contact[]> => {
    const rawList = await apiClient.get<any[]>(`/deals/${dealId}/contacts`);
    return rawList.map(mapContact);
  },

  create: async (dealId: string, data: CreateContactRequest): Promise<Contact> => {
    const raw = await apiClient.post<any>(`/deals/${dealId}/contacts`, data);
    return mapContact(raw);
  },

  update: async (contactId: string, data: UpdateContactRequest): Promise<Contact> => {
    const raw = await apiClient.patch<any>(`/contacts/${contactId}`, data);
    return mapContact(raw);
  },

  getFollowUps: async (): Promise<FollowUp[]> => {
    const rawList = await apiClient.get<any[]>('/outreach/follow-ups');
    return rawList.map(mapFollowUp);
  },
};
