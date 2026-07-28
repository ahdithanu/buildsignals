import { useQuery } from '@tanstack/react-query';
import { ingestionApi } from '@/api/ingestion';
import { queryKeys } from '@/lib/queryKeys';

export function usePermitDetail(permitId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.ingestion.permitDetail(permitId || ''),
    queryFn: () => ingestionApi.permitDetail(permitId!),
    enabled: !!permitId,
    retry: 1,
  });
}
