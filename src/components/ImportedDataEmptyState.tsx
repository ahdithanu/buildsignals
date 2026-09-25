import { ArrowRight, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { EmptyState, LoadingState } from '@/components/DataStates';
import { Button } from '@/components/ui/button';
import { useImportedRecordAvailability, type InventoryRecordTypes } from '@/hooks/useImportedRecordAvailability';

interface ImportedDataEmptyStateProps {
  recordTypes: InventoryRecordTypes;
  recordLabel: string;
  title: string;
  description: string;
  action?: ReactNode;
}

export function ImportedDataEmptyState({ recordTypes, recordLabel, title, description, action }: ImportedDataEmptyStateProps) {
  const inventory = useImportedRecordAvailability(recordTypes);
  if (inventory.isPending) return <LoadingState message="Checking imported records..." />;

  const unknown = !!inventory.error || inventory.data === undefined;
  return (
    <div className="px-4">
      <EmptyState
        title={unknown ? 'Imported data availability unknown' : inventory.data ? title : 'No imported records available'}
        description={unknown
          ? 'Stored inventory could not be confirmed. An empty result does not establish an absence of activity.'
          : inventory.data ? description
            : `No stored ${recordLabel} records were measured for this organization. Review source setup and collection status before drawing conclusions about activity.`}
        action={
          <div className="flex flex-wrap justify-center gap-2">
            {!unknown && inventory.data && action}
            <Button asChild variant="outline" size="sm">
              <Link to="/source-health">Open Source Health<ArrowRight className="h-3.5 w-3.5" /></Link>
            </Button>
            <Button variant="ghost" size="sm" disabled={inventory.isFetching} onClick={() => void inventory.refetch()}>
              <RefreshCw className={`h-3.5 w-3.5 ${inventory.isFetching ? 'animate-spin' : ''}`} />
              {unknown ? 'Retry inventory check' : 'Refresh inventory'}
            </Button>
          </div>
        }
      />
    </div>
  );
}
