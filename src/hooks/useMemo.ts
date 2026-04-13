import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { memosApi } from '@/api/memos';
import { queryKeys } from '@/lib/queryKeys';
import type { UpdateMemoRequest } from '@/types/memo';

export function useMemo(dealId: string) {
  return useQuery({
    queryKey: queryKeys.memos.get(dealId),
    queryFn: () => memosApi.get(dealId),
    enabled: !!dealId,
    retry: 1,
  });
}

export function useGenerateMemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dealId: string) => memosApi.generate(dealId),
    onSuccess: (_, dealId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.memos.get(dealId) });
    },
  });
}

export function useUpdateMemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ dealId, data }: { dealId: string; data: UpdateMemoRequest }) =>
      memosApi.update(dealId, data),
    onSuccess: (_, { dealId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.memos.get(dealId) });
    },
  });
}
