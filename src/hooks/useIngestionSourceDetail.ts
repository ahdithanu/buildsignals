import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ingestionApi } from '@/api/ingestion';
import { parcelReferencesApi } from '@/api/parcelReferences';
import { queryKeys } from '@/lib/queryKeys';

export function useIngestionSourceDetail(sourceId: string | undefined) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['ingestion', 'source-detail', sourceId || ''] as const,
    queryFn: async () => {
      const [health, runs, permits, sources] = await Promise.all([
        ingestionApi.sourceHealth(sourceId!),
        ingestionApi.runs(sourceId!),
        ingestionApi.permits(sourceId!),
        parcelReferencesApi.sources(),
      ]);
      const source = sources.find((candidate) => candidate.id === sourceId);
      const parcelSource = sources.find(
        (candidate) => candidate.record_type === 'parcel' && candidate.is_active,
      );
      const isPermitSource = source?.record_type === 'permit';
      const reconciliation = isPermitSource && parcelSource
        ? await parcelReferencesApi.reconciliation(sourceId!, parcelSource.id)
        : null;
      return {
        health,
        runs,
        permits,
        reconciliation,
        parcelSource,
        reconciliationUnavailable: Boolean(isPermitSource && !parcelSource),
      };
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
