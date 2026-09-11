import { beforeEach, describe, expect, it, vi } from 'vitest';
import { assessmentsApi } from '@/api/assessments';
import { apiClient } from '@/api/client';

vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

describe('Assessment history requests', () => {
  beforeEach(() => vi.resetAllMocks());
  it.each([
    ['revisions', '/signals/signal%2Fone/assessment-revisions'],
    ['reviews', '/assessment-revisions/signal%2Fone/reviews'],
    ['publication', '/assessment-revisions/signal%2Fone/publication'],
  ] as const)('encodes IDs and bounded page parameters for %s', (method, path) => {
    assessmentsApi[method]('signal/one', { limit: 21, skip: 40 });
    expect(apiClient.get).toHaveBeenCalledWith(`${path}?limit=21&skip=40`);
  });
  it('retains the legacy call without page parameters', () => {
    assessmentsApi.revisions('signal');
    expect(apiClient.get).toHaveBeenCalledWith('/signals/signal/assessment-revisions');
  });
});
