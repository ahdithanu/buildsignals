# Parcel Use Feasibility: Product Direction

## Owner Request (November15)

For parcels near retailer/development evidence, investigate potential land uses
and entitlement paths instead of presenting permit counts alone. The owner
reported interest from consulting peers. That is discovery feedback, not evidence
of paying customers or a validated prediction model.

## Evidence Contract Before Classification

Start with a qualified parcel identity and geometry, the responsible land-use
authority, a dated zoning designation and an applicable official use table/code.
Record evidence references, effective dates, source-use basis, and unresolved
conflicts. A zoning-code string on a parcel alone is insufficient to establish
permitted uses. A neighboring retailer or nearby filing is context, not approval
for the subject parcel or proof that it is for sale.

Proposed research categories are:

- Allowed under the cited current rules, subject to listed unresolved conditions.
- Conditional/discretionary review indicated by the cited rules.
- Not allowed under the cited current rules; no approval path established.
- Zoning change indicated by the cited rules.
- Unknown: missing, outdated, conflicting, or insufficient evidence.

Classification needs review of relevant overlays and parcel/site constraints;
do not infer capacity, access, utilities, setback compliance, subdivision rights,
or authority approval from proximity or a model's general knowledge. Separate
current zoning evidence, an analyst's possible entitlement path, and an actual
recorded decision. Explain uncertainty and route unresolved cases to diligence.

AI may extract/classify supported rule text and suggest research questions. It
must preserve references and unknowns; it cannot silently create verified parcel
facts or guarantee entitlement. Keep private ingestion configuration internal
without discarding backend provenance or required attribution.

## Next Qualification Slice

Pick one already requested market with an authorized parcel dataset, zoning
geometry and official dated use table. Demonstrate parcel-to-zone joins and
reviewed expected classifications before any paid-model evaluation. Measure
exact, ambiguous, unmatched and conflicting joins separately. Only then connect
the evidence to a nearby-parcel detail view and benchmark extraction/classification
against those reviewed examples. No model call, source activation, production
data change, or implemented entitlement classifier is claimed here.

## Local Recorded-Evidence Slice (November15)

The first UI/API slice is recorded zoning context on existing nearby-parcel
details, before permitted-use classification. GET `/parcels/{id}/use-context`
requires authentication, returns no-store, and independently scopes parcel,
source and raw-fact evidence to the current organization. Inactive or retired
parcels are unavailable. The fixed query reads at most 51 current zoning/land-use
facts (50 returned plus overflow detection); it never loads source configuration,
raw payloads or the existing unbounded detail/history helper.

Responses distinguish missing, reported, conflicting and incomplete evidence.
Canonical zoning strings remain recorded labels, never verified assignments.
Observation dates and confidence are provenance, not current ordinance/legal
verification. Raw evidence must match the parcel's tenant, source, external
identity and parcel record type; another parcel's evidence is not reusable.
Invalid values, dates, provenance or overflow fail closed to incomplete. Fact
JSON is bounded to16,384characters before decoding, with oversize/deep values
omitted and flagged incomplete. This is a projected-payload bound, not a database
storage/history or whole-query memory cap. No parcel/raw facts are changed, no source/model calls are made, and
no new migration or environment setting is needed. Demo access remains denied.

The panel uses an org/user/parcel-scoped query, runtime response validation, safe
HTTP(S) evidence links, and isolated retry. It does not infer allowed uses from
proximity, source labels or land-use descriptions. Every response explicitly
has `potential_uses=[]`, `potential_uses_status=not_assessed`, `ai_used=false`.
Assignment, effective use rules, overlays and site constraints stay unverified.

Cherry Hill's official map metadata identifies separate zoning, overlays and
redevelopment layers, but not a qualified current rules corpus or retained
parcel-to-zone joins. Read the November15 qualification note before advancing.
Next implementation gate is a dated, rights-reviewed full-geometry/rules capture
and reviewed one-use examples; centroid hits and map labels cannot establish
whole-parcel coverage. Keep split/ambiguous/unmatched/conflicting joins separate.

This slice is local only; final acceptance is recorded in the current handoff:
3,319backend/zero skips/91.51%,523frontend,13focused actualPG cases and fresh
Chrome desktop/mobile2passed. These prove synthetic read-path behavior, not
actual parcel zoning assignments, allowed uses or production acceptance.
