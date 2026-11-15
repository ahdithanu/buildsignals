# Failed Map Module Recovery

Local follow-up on recovery PR280, not part of either published PR and not
approved for publication, merge, deployment or production configuration changes.

## Observed Failure

The original fast-navigation production crash remains unverified. A bounded
synthetic, loopback-only Chrome investigation made twelve route clicks, including
six in519ms, without a page error, rejected promise or ErrorBoundary render.
Its final assertion initially treated expected pre-login401responses as failures;
the saved receipt passed the corrected error classification, not a new browser run.

A separate controlled abort of GeographicMap.tsx reproduced TypeError: Failed to
fetch dynamically imported module. React caught it through Lazy/Suspense and the
map panels. Try again produced another boundary catch with no additional module
request. This is a real application failure mechanism under a simulated network
failure, not evidence of missing production assets or deployment skew.

## Recovery Contract

Recognized dynamic-module TypeError messages now offer an explicit Reload page
action rather than retrying the rejected lazy import in the same document.
Reload is user-triggered only, warns that unsaved changes may be lost, and must
not create automatic reload loops or replay mutations. Ordinary render errors
retain Try again; the PR280 dashboard-recovery and modified-click behavior stay.

Unit regressions first produced3failures/10passes; final full frontend488passed
across75files7.50s, with13boundary cases. Typecheck/build/scoped ESLint pass;
known build annotation/chunk warnings remain. Independent product review passed.
The new real-API Chrome regression failed before the product change because the
Reload page button was absent, then passed1case2.4s/total7.5s after it. It proves
a new document at the same /map?state=CA URL, two module requests/one successful
response, a rendered synthetic marker, unchanged viewer session and no business
mutations or post-reload errors. External web/API traffic is blocked; basemap
tiles are intentionally unavailable. Browser servers/profiles were cleaned up.

This verifies development-module network failure in desktop Chrome, not a stale
hashed production bundle, Safari/Firefox runtime, publisher coverage or the
user's original failure. Their message variants have unit coverage only.
Read the newest handoff before continuing or publishing this local branch.
No changes to either published PR head, API, auth, tenant scope, data, source
jobs, paid models, platform settings or standing automation are authorized here.
