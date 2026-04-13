import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { contactsApi } from '@/api/contacts';
import { queryKeys } from '@/lib/queryKeys';
import type { CreateContactRequest, UpdateContactRequest } from '@/types/contact';

export function useContacts(dealId: string) {
  return useQuery({
    queryKey: queryKeys.contacts.list(dealId),
    queryFn: () => contactsApi.list(dealId),
    enabled: !!dealId,
    retry: 1,
  });
}

export function useCreateContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ dealId, data }: { dealId: string; data: CreateContactRequest }) =>
      contactsApi.create(dealId, data),
    onSuccess: (_, { dealId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.list(dealId) });
    },
  });
}

export function useUpdateContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ contactId, data }: { contactId: string; data: UpdateContactRequest }) =>
      contactsApi.update(contactId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contacts'] });
    },
  });
}

export function useFollowUps() {
  return useQuery({
    queryKey: queryKeys.contacts.followUps,
    queryFn: () => contactsApi.getFollowUps(),
    retry: 1,
  });
}
