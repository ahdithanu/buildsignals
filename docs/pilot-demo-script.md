# Pilot demo script (realtors / investor)

Purpose: a tight, honest walkthrough you can record this week. It leans on what
is real and live, and frames everything unproven as exactly that. Nothing here
claims for-sale inventory, verified parcels, or nationwide coverage.

Last verified live: 2026-10-17 against `https://www.buildsignals.ai`.

## What is real right now (say these plainly)

- **The product is live.** API on AWS App Runner; public read-only demo enabled
  at `https://www.buildsignals.ai` (`/v1/auth/demo` → `{"enabled":true}`).
- **We ingest real public data daily.** 16 bounded daily schedules run in AWS
  (14 regional FL/TX/AZ/GA permit & planning feeds + Columbus production + a
  separate demo refresh). These are real planning/permit **events**, not parcels
  or listings.
- **The demo shows a real historical cohort:** ~2,104 Columbus filing records,
  5,045 graph entities, 8,403 relationships, 1,088 reported parcel references.
- **Filings now map.** 938 demo filings carry derived coordinates
  (Census address-range estimate); the demo map renders them (100 per layer).

## What is deliberately not claimed (say these too — it builds trust)

- Nearby parcels are **investigation leads**, not for-sale inventory. A parcel is
  only "verified available" with a broker/listing/owner source — otherwise it is
  a place to look, not a listing.
- Reported parcel references are not qualified parcel matches; qualified parcel
  geometry and county data-use rights are still pending (so `parcel_records` = 0).
- Collection recency ≠ filing recency; we show when a record was collected vs its
  source/filing date separately and never pass one off as the other.

## Recording sequence (≈5 minutes)

1. **Open the demo** at `https://www.buildsignals.ai` → "Enter demo mode" (no
   credentials; read-only banner visible). Frame: "public records, one workflow:
   signal → evidence → map → opportunity."
2. **Signals.** Open the Signals list; pick a Columbus development filing. Show
   the source link and that every datum is evidence-backed, not inferred.
3. **Evidence graph.** Open the opportunity graph: companies, locations, parcels,
   and relationships, each with source rationale. This is the "why we believe it."
4. **Map.** Switch to the map — ~100 geocoded filings plotted across Columbus.
   Say: "these are real filing locations; the dots are where development activity
   is being proposed, before it's obvious."
5. **Acquisition workflow.** Walk the strip: Alert → Evidence → Review → Owner →
   Outreach → Follow-up → Saved. Emphasize parcels here are leads to investigate.
6. **Screening + export.** Show a buy-box screen (pass/fail/unknown with reasons)
   and the downloadable, evidence-attributed snapshot. Honesty: unknowns stay
   unknown; an analyst note is not a verified fact.
7. **The pitch close.** "Live daily ingestion of public development signals across
   several states, turned into an investigable, source-cited workflow. Parcel
   availability and diligence verification are the paid next step."

## Talking points for the investor

- Moat: evidence-first provenance (every signal cites its source) + a normalized
  cross-jurisdiction graph, not a scraped list.
- Honest coverage: cite the live schedule count and measured demo counts above;
  do not quote nationwide or unique-project numbers.
- Roadmap you can defend: qualified parcel sources + use rights, verified
  availability feeds, and independent diligence verification are the funded path.

## Known demo limitations to pre-empt

- Map is Columbus-only in the demo cohort (regional live data sits in the
  authenticated workspace, kept separate from the public demo).
- Parcels are not plotted (no qualified parcel geometry yet) — expected.
- Map shows 100 points per layer (display cap), not all 938 geocoded filings.
