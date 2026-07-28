import { describe, expect, it } from 'vitest';

import { buildIngestionReliabilitySummary } from '@/lib/ingestionReliability';

describe('buildIngestionReliabilitySummary', () => {
  it('counts active reliability concerns for the operations page', () => {
    const summary = buildIngestionReliabilitySummary(
      [
        {
          source_id: 'source-1',
          source_key: 'live_permits',
          source_name: 'Live Permits',
          attribution_required: false,
          share_alike_review_required: false,
          status: 'critical',
          active_run_stale: true,
          cursor_stalled: true,
          terminal_runs: 3,
          unhealthy_runs: 2,
          records_seen: 120,
          records_failed: 8,
          reasons: ['Heartbeat stale'],
        },
        {
          source_id: 'source-2',
          source_key: 'parcel_feed',
          source_name: 'Parcel Feed',
          attribution_required: false,
          share_alike_review_required: false,
          status: 'healthy',
          active_run_stale: false,
          cursor_stalled: false,
          terminal_runs: 2,
          unhealthy_runs: 0,
          records_seen: 40,
          records_failed: 0,
          reasons: [],
        },
      ] as any,
      [
        {
          key: 'candidate-1',
          name: 'Retry Candidate',
          adapter: 'csv',
          record_type: 'parcel',
          jurisdiction: 'Texas',
          base_url: 'https://example.gov/parcel',
          official_landing_page: 'https://example.gov/parcel',
          license: 'Public',
          status: 'operational_retry',
          blocker_summary: 'Retry needed',
          early_warning_value: 'Parcel source',
          candidate_source_fields: ['id'],
          can_run_canary: true,
          last_canary_ok: false,
          last_checked_on: '2026-07-23',
          next_audit_on: '2026-07-24',
          notes: 'Retry candidate',
        },
      ] as any,
    );

    expect(summary.healthy).toBe(1);
    expect(summary.attention).toBe(0);
    expect(summary.critical).toBe(1);
    expect(summary.queued).toBe(1);
    expect(summary.blocked).toBe(0);
    expect(summary.staleRuns).toBe(1);
    expect(summary.stalledCursors).toBe(1);
    expect(summary.failedRetryCanaries).toBe(1);
    expect(summary.watchlistSources[0].source_name).toBe('Live Permits');
  });
});
