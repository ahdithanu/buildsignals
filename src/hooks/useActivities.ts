import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { activitiesApi } from '@/api/activities';
import { queryKeys } from '@/lib/queryKeys';
import type { CreateActivityRequest } from '@/types/activity';

export function useActivities(dealId: string) {
  return useQuery({
    queryKey: queryKeys.activities.list(dealId),
    queryFn: () => activitiesApi.list(dealId),
    enabled: !!dealId,
    retry: 1,
  });
}

export function useCreateActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ dealId, data }: { dealId: string; data: CreateActivityRequest }) =>
      activitiesApi.create(dealId, data),
    onSuccess: (_, { dealId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.activities.list(dealId) });
    },
  });
}
