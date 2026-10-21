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
