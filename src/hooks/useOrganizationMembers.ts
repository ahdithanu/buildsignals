import { useQuery } from '@tanstack/react-query';
import { organizationsApi } from '@/api/organizations';
import { queryKeys } from '@/lib/queryKeys';

export function useOrganizationMembers(orgId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.organizations.members(orgId || ''),
    queryFn: () => organizationsApi.listMembers(orgId!),
    enabled: !!orgId,
    retry: 1,
  });
}
