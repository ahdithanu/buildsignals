# Dallas Legistar Planning Agendas Production Review

## Decision

Approved on 2026-08-24 for bounded storage of public City of Dallas planning
agenda fields and customer-facing derived intelligence with official source
attribution. Attachments, raw agenda or minutes documents, and raw-source
replacement exports remain prohibited.

## Canary Evidence

- The production candidate-canary path fetched 10 records, normalized all 10,
  reported zero failures, and observed 10 `hearing_scheduled` signals.
- Every sampled record retained a stable client/event/item identity, official
  matter or file reference, evidence excerpt, publisher timestamp, and source
  URL.
- Newest-first ordering produced a latest publisher timestamp within the
  reviewed 14-day civic-publication SLA.
- A bounded one-year decision probe inspected all 21 City Plan Commission
  events available in the window and found no minutes or action payloads.
  Dallas Legistar is therefore approved only as a pre-approval agenda source.

## Controls

- One exact host: `webapi.legistar.com`.
- Daily collection; 45-day lookback and 120-day forward meeting window.
- Maximum 40 events, 150 items per event, 250 records, and 10,000 evidence
  characters per record.
- Agenda and minutes notes may be requested, but attachments are always
  disabled and suppressed.
- Items without a positive Legistar matter ID or official file/reference number
  are discarded.
- Immutable source versions preserve corrections and removals. A disappearance
  or meeting cancellation is not treated as project withdrawal.

Existing permit sources remain the approval and issuance confirmation layer.
Planning decisions require a separately validated official Dallas minutes
source before they may be represented as `decision_recorded`.
