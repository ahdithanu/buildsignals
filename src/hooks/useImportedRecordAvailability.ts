import { useQuery } from '@tanstack/react-query';
import { ingestionApi } from '@/api/ingestion';
import { useAuth } from '@/contexts/AuthContext';
import type { CoverageRecordType } from '@/types/ingestion';

const PAGE_SIZE = 100;
export type InventoryRecordTypes = readonly [CoverageRecordType, ...CoverageRecordType[]];

export function useImportedRecordAvailability(recordTypes: InventoryRecordTypes) {
  const { organizationId, isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['ingestion', 'imported-record-availability', organizationId, recordTypes],
    queryFn: async ({ signal }) => {
      for (const recordType of recordTypes) {
        let offset = 0;
        // A zero source page cannot establish an empty organization inventory.
        while (true) {
          if (signal.aborted) throw new Error('Inventory check cancelled.');
          const page = await ingestionApi.measuredCoverage({
            record_type: recordType, freshness_hours: 72, limit: PAGE_SIZE, offset,
          });
          if (signal.aborted) throw new Error('Inventory check cancelled.');
          if (page.sources.some(source => source.stored_records > 0)) return true;
          if (!page.has_more) break;
          offset += PAGE_SIZE;
        }
      }
      return false;
    },
    enabled: isAuthenticated && !!organizationId,
    staleTime: 60_000,
    retry: 1,
  });
}
