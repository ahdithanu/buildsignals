import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { parcelsApi } from '@/api/parcels';
import type { AcquisitionRadarParams, ParcelReviewStatus } from '@/types/parcel';

export function useAcquisitionRadar(params: AcquisitionRadarParams) {
  const queryClient = useQueryClient();
  const radar = useQuery({
    queryKey: ['acquisition-radar', params],
    queryFn: () => parcelsApi.radar(params),
  });
  const review = useMutation({
    mutationFn: ({ candidateId, reviewStatus }: {
      candidateId: string;
      reviewStatus: ParcelReviewStatus;
    }) => parcelsApi.review(candidateId, reviewStatus),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['acquisition-radar'] }),
  });
  return { ...radar, review };
}
