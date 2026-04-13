import { useQuery } from '@tanstack/react-query';
import { dealsApi } from '@/api/deals';
import { queryKeys } from '@/lib/queryKeys';

export function useDealDetail(dealId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.deals.detail(dealId || ''),
    queryFn: () => dealsApi.get(dealId!),
    enabled: !!dealId,
    retry: 1,
  });
}
