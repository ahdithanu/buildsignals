import { useQuery } from '@tanstack/react-query';
import { ingestionApi } from '@/api/ingestion';
import { useAuth } from '@/contexts/AuthContext';
import type { CoverageRecordType } from '@/types/ingestion';

export type InventoryRecordTypes = readonly [CoverageRecordType, ...CoverageRecordType[]];

export function useImportedRecordAvailability(recordTypes: InventoryRecordTypes) {
  const { organizationId, isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['ingestion', 'imported-record-availability', organizationId, recordTypes],
    queryFn: async ({ signal }) => {
      for (const recordType of recordTypes) {
        if (signal.aborted) throw new Error('Inventory check cancelled.');
        const summary = await ingestionApi.coverageSummary(recordType);
        if (signal.aborted) throw new Error('Inventory check cancelled.');
        if (summary.stored_records > 0) return true;
      }
      return false;
    },
    enabled: isAuthenticated && !!organizationId,
    staleTime: 60_000,
    retry: 1,
  });
}
