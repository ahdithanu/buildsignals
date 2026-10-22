# Parcel Discovery Readiness

Build Signals treats parcel discovery as a staged evidence workflow. A map
point is not automatically an acquisition opportunity.

## Readiness stages

The authenticated `GET /acquisition-map/readiness` endpoint reports the
workspace stage using the following precedence:

| Stage | Meaning | Next action |
| --- | --- | --- |
| `signals_not_geocoded` | Permit and planning records do not have usable coordinates. | Ingest or geocode signals. |
| `parcel_records_not_geocoded` | Signals are located, but parcel records are not. | Ingest geocoded parcel records for the target jurisdictions. |
| `search_not_run` | Both layers are located, but no bounded nearby search has been saved. | Run a search from a geocoded signal. |
| `no_nearby_matches` | A search exists but produced no non-dismissed parcel records. | Review radius, filters, and source coverage. |
| `candidates_need_availability_evidence` | Nearby parcel leads exist, but none has qualifying source-backed availability evidence. | Attach listing, broker, owner, or auction evidence. |
| `verified_available_candidates` | At least one nearby candidate has qualifying availability evidence. | Review and move qualified parcels into acquisition workflow. |

## Count semantics

- `nearby_candidate_parcels` counts distinct non-dismissed parcel records
  returned by saved nearby searches.
- `verified_available_parcels` counts active parcel records with a current
  availability fact that has an explicit status, evidence type, confidence of
  at least `0.7`, and a source URL or excerpt.
- `nearby_verified_available_parcels` is the intersection of those two sets.
- Neither candidate count nor parcel-source configuration implies that a site
  is for sale. Availability must be independently evidenced.

## Scaling path

This contract is deliberately source-agnostic. State expansion should add
parcel connectors and measured coverage without changing the discovery API.
Availability connectors can later replace or supplement manual evidence, but
must produce the same source-backed `ParcelFact` contract. That keeps ranking,
review, export, and customer-facing claims independent from any one listing
provider.

## Bulk availability intake

`POST /parcel-availability/import` accepts up to 500 evidence rows for a
workspace. Each row must include `source_id` and `external_parcel_id`; the
service will not match by address or infer identity across parcel sources.
Rows that do not match an active parcel are returned as skipped row errors.
Valid rows use the same evidence validation, immutable raw receipt, current
fact replacement, and audit logging as the single-parcel endpoint.

## Nationwide parcel gap report

`GET /ingestion/coverage/national-parcels` is the control-plane view for the
50-state parcel expansion. It deliberately separates four postures:

- `measured`: stored parcel records were observed for the state.
- `configured_only`: an active parcel source is configured, but no stored
  parcel records were measured for the state.
- `candidate_only`: source research exists, but the source is not admitted to
  the active catalog.
- `uncovered`: neither an active source nor a candidate source is recorded.

Each state also reports nearby parcel candidates and verified available parcels.
The latter requires the same source-backed availability contract described
above; a parcel candidate never becomes a listing by inference. The response
includes a bounded `next_connector_targets` queue that prioritizes candidate
sources and configured-but-empty states before unresearched states. It is a
read-only measurement: it does not run a connector, promote a candidate, or
clear a legal or technical hold.
