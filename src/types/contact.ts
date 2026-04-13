export interface Contact {
  id: string;
  dealId: string;
  name: string;
  role: string;
  company: string;
  email: string;
  phone: string;
  notes: string;
  lastContacted: string;
}

export interface CreateContactRequest {
  name: string;
  role?: string;
  company?: string;
  email?: string;
  phone?: string;
  notes?: string;
}

export interface UpdateContactRequest {
  name?: string;
  role?: string;
  company?: string;
  email?: string;
  phone?: string;
  notes?: string;
}

export interface FollowUp {
  id: string;
  contactId: string;
  contactName: string;
  dealName: string;
  dealId: string;
  dueDate: string;
  note: string;
  completed: boolean;
}
