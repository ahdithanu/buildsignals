import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { parcelsApi } from '@/api/parcels';
import type {
  AcquisitionRadarParams,
  ParcelAcquisitionActivityCreate,
  ParcelAcquisitionCaseUpdate,
} from '@/types/parcel';

export function useAcquisitionRadar(params: AcquisitionRadarParams) {
  const queryClient = useQueryClient();
  const radar = useQuery({
    queryKey: ['acquisition-radar', params],
    queryFn: () => parcelsApi.radar(params),
  });
  const updateCase = useMutation({
    mutationFn: ({ caseId, payload }: {
      caseId: string;
      payload: ParcelAcquisitionCaseUpdate;
    }) => parcelsApi.updateAcquisitionCase(caseId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['acquisition-radar'] }),
  });
  const recordActivity = useMutation({
    mutationFn: ({ caseId, payload }: {
      caseId: string;
      payload: ParcelAcquisitionActivityCreate;
    }) => parcelsApi.recordAcquisitionActivity(caseId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['acquisition-radar'] }),
  });
  const promote = useMutation({
    mutationFn: ({ candidateId, name }: { candidateId: string; name?: string }) =>
      parcelsApi.promote(candidateId, { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['acquisition-radar'] }),
  });
  const exportSearch = useMutation({
    mutationFn: (searchId: string) => parcelsApi.exportSearch(searchId),
  });
  return { ...radar, updateCase, recordActivity, promote, exportSearch };
}
