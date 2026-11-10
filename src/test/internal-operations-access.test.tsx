import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { apiClient } from '@/api/client';
import { parcelReferencesApi } from '@/api/parcelReferences';
import { ingestionApi } from '@/api/ingestion';
import { useCandidateCanaryHistory, useIngestionCoverage, useIngestionHealth, useIngestionHostPolicy, useIngestionSchedulePlan, useNationalParcelCoverage } from '@/hooks/useIngestionHealth';
import { useIngestionSourceDetail } from '@/hooks/useIngestionSourceDetail';
import { useMeasuredCoverage } from '@/hooks/useMeasuredCoverage';

const auth = vi.hoisted(() => ({ organizationId: 'org', isAuthenticated: true, role: 'admin', isInternalOperator: false }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>;

beforeEach(() => { vi.clearAllMocks(); auth.isInternalOperator = false; vi.mocked(apiClient.get).mockResolvedValue([]); });

it('never fetches raw operations for an ordinary customer admin', async () => {
  const { result } = renderHook(() => [
    useIngestionHealth(), useIngestionCoverage(), useIngestionHostPolicy(), useIngestionSchedulePlan(),
    useCandidateCanaryHistory('candidate', true), useIngestionSourceDetail('source'),
    useMeasuredCoverage({ record_type: 'permit', freshness_hours: 72, limit: 100, offset: 0 }),
  ], { wrapper });
  await waitFor(() => expect(result.current.every(query => query.fetchStatus === 'idle')).toBe(true));
  expect(apiClient.get).not.toHaveBeenCalled();
});

it('keeps customer geographic parcel coverage enabled', async () => {
  renderHook(() => useNationalParcelCoverage(), { wrapper });
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/ingestion/coverage/national-parcels'));
});

it('fetches operations for an explicitly authorized operator', async () => {
  auth.isInternalOperator = true;
  renderHook(() => useIngestionSchedulePlan(), { wrapper });
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/ingestion/schedule-plan', undefined));
});

it('uses the narrow customer-safe selector instead of the connector inventory', async () => {
  await parcelReferencesApi.sourceOptions();
  expect(apiClient.get).toHaveBeenCalledExactlyOnceWith('/ingestion/source-options');
});

it('uses aggregate inventory rather than measured connector inventory for customer counts', async () => {
  await ingestionApi.coverageSummary('planning');
  expect(apiClient.get).toHaveBeenCalledExactlyOnceWith('/ingestion/coverage/summary', { record_type: 'planning' });
});
