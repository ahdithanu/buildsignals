# BuildSignals ForgeOS Project Profile

Adopted November20,2026 for local engineering under the owner's instruction.
This profile and `forgeos-delivery-loop.md` are self-contained operating rules;
a sibling ForgeOS checkout is not required to run tests or resume work. Reviewed
source paths and exact SHA-256 pins live in `.forgeos/adoption.json`. The source
directory really is named `governence`; do not silently correct its spelling.
Changes to upstream playbooks require review, not automatic policy replacement.

## Principles Applied Here

- Correctness before speed; evidence before assumptions; simplicity before cleverness.
- Document the intended behavior before implementation and test before completion.
- Preserve maintainability, security, tenant isolation and source evidence by default.
- Make ordinary reversible engineering decisions without repeated permission prompts.
- Use disjoint multi-agent lanes, independent review and one integration owner.
- Continue the next unblocked existing slice after each checkpoint.
- Human approval remains required for production changes and material security,
  rights, cost or product decisions. Local acceptance is not release authority.

## Product Contract

BuildSignals helps acquisition teams investigate development activity and nearby
parcels. The acceptance path is a real retail filing, its evidence and location,
a bounded nearby-parcel search, parcel facts/zoning gaps, then a saved acquisition
candidate. A permit is not a project or opening. An APN is not necessarily a
distinct developable lot. A nearby candidate is not a listing or an entitlement.

Keep source snapshots, identifiers, timestamps, matching methods and review
decisions. Customer access must not reveal the owner-only ingestion console;
that restriction does not permit removal of required attribution or evidence.
Missing coordinates, freshness, zoning rules, financial inputs and availability
remain explicit unknowns. Never fabricate inventory or ground truth for a demo.

## Existing-Stack Decisions

These document the inherited implementation rather than ordering a migration.
They do not relax correctness, security or verification requirements.

| Area | BuildSignals decision | Reason and future trigger |
| --- | --- | --- |
| Python | Preserve the Python3.11 Docker/CI baseline; ForgeOS backend playbook recommends3.13+ | Runtime upgrade needs a dedicated compatibility slice, not incidental adoption churn. |
| Backend boundaries | FastAPI routes, services, SQLAlchemy models and Alembic in the existing layered monolith | Do not reorganize into domains/repositories merely to match a template; introduce boundaries when a demonstrated workflow benefits. |
| Frontend | Preserve React18, TypeScript, Vite, React Router, TanStack Query, Tailwind and shadcn/ui | Existing routes and components are the presentation contract; typed integration and focused fixes take priority over redesign. |
| Persistence/graph | PostgreSQL/PostGIS with organization scope, RLS and evidence-linked graph tables | No Neo4j migration or separate graph service is implied by the word graph. |
| Deployment | Vercel frontend, AWS App Runner API and separately scheduled ingestion workers in the last verified deployment | Render configuration is not proof of the active runtime. Verify current targets before any approved release. |
| Models | Existing OpenRouter client; deterministic scoring default; optional research SDK isolated | No paid calls or SDK/app dependency upgrades as part of adoption or offline tests. |

## Acceptance And Evidence

Every slice records its exact branch/head, commands, results, warnings, data
origin, scope and next dependency. Distinguish implemented, locally tested,
hosted-tested, merged, deployed and production-verified states. A green synthetic
browser fixture is not a real customer workflow receipt. SQLite tests alone do
not prove PostgreSQL row isolation, locks or spatial behavior.

Real retail-to-parcel acceptance requires:

1. A retained real filing with source evidence and reviewable retailer identity.
2. A qualified native location, or an explicitly labelled estimate that cannot
   silently become a verified parcel-search anchor.
3. Existing ingestion/normalization for the parcels, with scoped IDs, raw/graph
   evidence and correct physical-group semantics; no raw database fixture inserts
   presented as successful ingestion.
4. A bounded search that persists inputs and candidate snapshots, preserves
   identity confidence independently of proximity and supports safe retry.
5. Parcel detail with evidence, location method, zoning/rule gaps and unknown
   sale status. No unsupported AI permitted-use or investment-return claim.
6. Explicit shortlist/promotion into a saved opportunity with traceable links,
   tenant isolation, demo write denial and duplicate protection.
7. Desktop/mobile browser proof on the actual API; production acceptance is
   separately authorized and recorded, never inferred from a local fixture.

## Current Constraints

At adoption, PR288 is merged93435f6 and its API/frontend release has HTTP/proxy
acceptance. Fresh signed-in visual acceptance and current main-workspace counts
remain unverified. Last parcel receipt is838records, not838distinct lots; the
historical demo is separate. SF native filing mapping and Wake qualification
remain local work with their own gates. See the newest handoff for receipts.
Cherry Hill inquiry stays DRAFT/UNSENT. Existing one-shot grants are consumed.

Run `python3 scripts/agent_status.py --check` offline at session start. When the
authoritative checkout is available, explicitly add
`--forgeos-root /path/to/ForgeOS` to verify upstream pins. Neither command may
fetch, read secrets, call a model or change production.
