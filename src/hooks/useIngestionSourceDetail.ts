import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ingestionApi } from '@/api/ingestion';
import { queryKeys } from '@/lib/queryKeys';

export function useIngestionSourceDetail(sourceId: string | undefined) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['ingestion', 'source-detail', sourceId || ''] as const,
    queryFn: async () => {
      const [health, runs, permits] = await Promise.all([
        ingestionApi.sourceHealth(sourceId!),
        ingestionApi.runs(sourceId!),
        ingestionApi.permits(sourceId!),
      ]);
      return { health, runs, permits };
    },
    enabled: !!sourceId,
    retry: 1,
    staleTime: 30_000,
  });
  const canary = useMutation({
    mutationFn: ({ sampleSize = 10 }: { sampleSize?: number }) =>
      ingestionApi.canary(sourceId!, sampleSize),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ingestion', 'source-detail', sourceId || ''] });
      queryClient.invalidateQueries({ queryKey: ['ingestion', 'health'] });
    },
  });
  return { ...query, canary };
}
