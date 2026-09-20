import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { parcelsApi } from '@/api/parcels';
import { queryKeys } from '@/lib/queryKeys';
import { useAuth } from '@/contexts/AuthContext';
import type {
  NearbyParcelCandidateAssignment,
  NearbyParcelOpportunityCreate,
  NearbyParcelSearchCreate,
  ParcelPersona,
  ParcelReviewStatus,
} from '@/types/parcel';

export function selectLatestNearbyParcelSearch(
  history: Array<{ id: string; persona: ParcelPersona; created_at: string }> | undefined,
  persona: ParcelPersona,
) {
  if (!history || history.length === 0) return undefined;
  const matchingPersona = history.filter((search) => search.persona === persona);
  const candidates = matchingPersona.length > 0 ? matchingPersona : history;
  return [...candidates].sort(
    (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
  )[0];
}

export function useNearbyParcels(dealId: string | undefined, persona: ParcelPersona) {
  const { organizationId, user } = useAuth();
  const scope = [organizationId, user?.id] as const;
  const queryClient = useQueryClient();
  const history = useQuery({
    queryKey: [...queryKeys.parcels.history(dealId || ''), ...scope],
    queryFn: () => parcelsApi.history(dealId!),
    enabled: !!dealId && !!organizationId && !!user,
  });
  const latestForPersona = selectLatestNearbyParcelSearch(history.data, persona);
  const latestId = latestForPersona?.id || history.data?.[0]?.id;
  const search = useQuery({
    queryKey: [...queryKeys.parcels.search(latestId || ''), ...scope],
    queryFn: () => parcelsApi.get(latestId!),
    enabled: !!latestId && !!organizationId && !!user,
  });
  const refreshRadar = async () => {
    await queryClient.invalidateQueries({ queryKey: ['acquisition-radar', ...scope] });
    await queryClient.invalidateQueries({ queryKey: ['map-readiness', organizationId] });
  };
  const create = useMutation({
    mutationFn: (payload: NearbyParcelSearchCreate) => parcelsApi.create(dealId!, payload),
    onSuccess: async (created) => {
      queryClient.setQueryData([...queryKeys.parcels.search(created.id), ...scope], created);
      await queryClient.invalidateQueries({ queryKey: [...queryKeys.parcels.history(dealId || ''), ...scope] });
      await refreshRadar();
    },
  });
  const review = useMutation({
    mutationFn: ({ candidateId, status }: { candidateId: string; status: ParcelReviewStatus }) =>
      parcelsApi.review(candidateId, status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: [...queryKeys.parcels.search(latestId || ''), ...scope] });
      await refreshRadar();
    },
  });
  const assign = useMutation({
    mutationFn: ({ candidateId, payload }: { candidateId: string; payload: NearbyParcelCandidateAssignment }) =>
      parcelsApi.assign(candidateId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: [...queryKeys.parcels.search(latestId || ''), ...scope] });
      await refreshRadar();
    },
  });
  const promote = useMutation({
    mutationFn: ({ candidateId, payload }: { candidateId: string; payload: NearbyParcelOpportunityCreate }) =>
      parcelsApi.promote(candidateId, payload),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: [...queryKeys.parcels.search(latestId || ''), ...scope] });
      await refreshRadar();
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.parcels.history(result.deal.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.graph.opportunityContext(result.deal.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.graph.entityDetail(result.deal.id) });
    },
  });
  const exportSearch = useMutation({
    mutationFn: (searchId: string) => parcelsApi.exportSearch(searchId),
  });
  return { history, search, create, review, assign, promote, exportSearch };
}
