import { useState } from 'react';
import { useQuery, type QueryKey } from '@tanstack/react-query';
import type { HistoryPage } from '@/api/assessments';

export const ASSESSMENT_HISTORY_PAGE_SIZE = 20;

export function useAssessmentHistory<T>(queryKey: QueryKey, load: (page: HistoryPage) => Promise<T[]>, enabled: boolean) {
  const [page, setPage] = useState(0);
  const query = useQuery({
    queryKey: [...queryKey, 'history', page],
    // A single look-ahead row avoids guessing whether another page exists.
    queryFn: () => load({ limit: ASSESSMENT_HISTORY_PAGE_SIZE + 1, skip: page * ASSESSMENT_HISTORY_PAGE_SIZE }),
    enabled,
  });
  return {
    ...query,
    rows: query.isError ? undefined : query.data?.slice(0, ASSESSMENT_HISTORY_PAGE_SIZE),
    page,
    hasNext: !query.isError && (query.data?.length ?? 0) > ASSESSMENT_HISTORY_PAGE_SIZE,
    setPage,
  };
}
