import { useQuery } from '@tanstack/react-query';
import { parcelsApi } from '@/api/parcels';
import { queryKeys } from '@/lib/queryKeys';

export function useParcelDetail(parcelId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.parcels.detail(parcelId || ''),
    queryFn: () => parcelsApi.detail(parcelId!),
    enabled: !!parcelId,
    retry: 1,
  });
}
