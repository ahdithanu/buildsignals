# Error Screen Recovery

Recovery checkpointae5ce92 on merged mainc34cef4; generated-schema main9f09d87
is integrated without runtime changes. Separate PR publication and checks are
approved; merge and release are not. See PR metadata for hosted results.

The user reported a full error screen during fast navigation. Fresh normal
Chrome checks across Map, Planning, Brands, Signals, Watchlist and Graph did not
reproduce the initial exception. Exact failing URL/clicks are still required.
Message-channel closure logs are not evidence of an application root cause.

A separate recovery defect was reproduced with the actual ErrorBoundary,
InternalError and React Router: after a synthetic render exception, clicking
Back to dashboard changed the route but left the boundary latched. The new
regression failed before the fix. The dashboard link now invokes the existing
reset handler for an unmodified same-tab left click that navigates to the
dashboard. Modified/middle clicks do not retry the current failed route. Try again
keeps its existing behavior. No automatic retry, paid call, authentication,
tenant isolation, API or data behavior is changed.

This addresses error-screen recovery, not the unverified live crash trigger.
Read the current handoff for tests/review and release status. Do not claim the
production crash is fixed until its exception is captured and verified.
