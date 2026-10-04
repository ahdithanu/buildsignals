"""Descriptive source counts, not a validated Development Velocity signal."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.ingestion import IngestionSource, RawSourceRecord
from app.models.temporal import TemporalObservation
from app.schemas.activity_baseline import ActivityBaselineRequest
from app.services.temporal_service import fingerprint, utc
from app.utils.org_scope import get_org_id

METHODOLOGY_VERSION = "permit-activity-baseline-v1"
MAX_COHORT_ROWS = 20000
MAX_HISTORY_ROWS = 50000
EVIDENCE_SAMPLE_SIZE = 5
WARNINGS = [
    "Historical source completeness is unverified; counts are not a market-growth signal or investment score.",
    "Counts describe source records, not unique projects. Overlapping sources are not summed.",
    "Only evidence received and interpreted by as_of is included; backfilled history was not known earlier.",
    "Windows use UTC boundaries and exclude the current day plus the selected reporting lag.",
    "Reporting lag is a user-selected allowance, not a verified source-latency guarantee.",
    "City matching is exact after whitespace/case normalization; this is not metropolitan coverage.",
]


def _name(value: object) -> str:
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def activity_baseline(db: Session, request: ActivityBaselineRequest) -> dict:
    try:
        as_of = utc(request.as_of)
    except OverflowError as exc:
        raise ValueError("as_of exceeds the supported UTC date range") from exc
    if as_of > datetime.now(timezone.utc):
        raise ValueError("as_of cannot be in the future")
    duration = timedelta(days=request.period_days)
    try:
        end = as_of.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=request.reporting_lag_days)
        start = end - duration * (request.baseline_periods + 1)
    except OverflowError as exc:
        raise ValueError("Comparison windows precede the supported date range") from exc
    org_id = get_org_id()
    pins = sorted(request.sources, key=lambda pin: pin.source_id)
    available = set(db.scalars(select(IngestionSource.id).where(
        IngestionSource.organization_id == org_id,
        IngestionSource.id.in_([pin.source_id for pin in pins]),
    )))
    if available != {pin.source_id for pin in pins}:
        raise LookupError("Source cohort not found")

    canonical_request = request.model_dump(mode="json")
    canonical_request.update(
        as_of=as_of.isoformat(), city=_name(request.city),
        sources=[pin.model_dump() for pin in pins],
    )
    result = dict(
        methodology_version=METHODOLOGY_VERSION,
        request_fingerprint=fingerprint([org_id, METHODOLOGY_VERSION, canonical_request]),
        as_of=as_of, city=request.city, state=request.state, attribute=request.attribute,
        status="coverage_unverified", sources=[], score=None, warnings=list(WARNINGS),
    )

    observation = TemporalObservation
    raw = RawSourceRecord
    # Choose the latest known interpretation BEFORE date/geography filtering. A
    # correction that clears a filing date or moves a project must remove the old count.
    eligible = select(
        observation.id,
        observation.source_id,
        observation.recorded_at,
        raw.external_record_id,
    ).join(raw, and_(
        raw.id == observation.raw_source_record_id,
        raw.organization_id == observation.organization_id,
        raw.source_id == observation.source_id,
    )).where(
        observation.organization_id == org_id,
        raw.organization_id == org_id,
        observation.attribute == request.attribute,
        observation.source_type == "permit",
        raw.record_type == "permit",
        observation.first_observed_at <= as_of,
        observation.recorded_at <= as_of,
        raw.received_at <= as_of,
        or_(*(and_(
            observation.source_id == pin.source_id,
            observation.methodology_version == pin.methodology_version,
        ) for pin in pins)),
    ).limit(MAX_HISTORY_ROWS + 1).cte("eligible_history")
    # Bound input to window ranking, not just output. The count comes from the
    # same statement/snapshot; an overflow withholds all sampled results.
    ranked = select(
        eligible.c.id, eligible.c.external_record_id,
        select(func.count()).select_from(eligible).scalar_subquery().label("history_count"),
        func.dense_rank().over(
            partition_by=(eligible.c.source_id, eligible.c.external_record_id),
            order_by=eligible.c.recorded_at.desc(),
        ).label("recency"),
    ).subquery()
    rows = db.execute(select(observation, ranked.c.external_record_id, ranked.c.history_count).join(
        ranked, ranked.c.id == observation.id,
    ).where(ranked.c.recency == 1, observation.organization_id == org_id).order_by(
        observation.source_id, ranked.c.external_record_id, observation.id,
    ).limit(MAX_COHORT_ROWS + 1)).all()
    if len(rows) > MAX_COHORT_ROWS or (rows and rows[0].history_count > MAX_HISTORY_ROWS):
        result.update(status="bounded_query_exceeded")
        result["warnings"].append("Cohort exceeds the latest-record or history-row limit; no partial counts were calculated. Narrow the source cohort.")
        return result

    rows = [(row, key) for row, key, _ in rows]
    multiplicity = Counter((row.source_id, external_id) for row, external_id in rows)
    for pin in pins:
        source_rows = [(row, key) for row, key in rows if row.source_id == pin.source_id]
        windows = [dict(
            start=start + duration * index, end=start + duration * (index + 1),
            role="current" if index == request.baseline_periods else "baseline",
            observed_records=0, evidence_observation_ids=[],
        ) for index in range(request.baseline_periods + 1)]
        diagnostics = Counter()
        ambiguous = set()
        for row, external_id in source_rows:
            if multiplicity[(row.source_id, external_id)] > 1:
                ambiguous.add(external_id)
                continue
            geo = row.geography if isinstance(row.geography, dict) else {}
            if not _name(geo.get("city")) or not _name(geo.get("state")):
                diagnostics["missing_geography"] += 1
                continue
            if _name(geo["city"]) != _name(request.city) or _name(geo["state"]) != _name(request.state):
                diagnostics["outside_geography"] += 1
                continue
            if row.value is None or row.effective_at is None:
                diagnostics["missing_or_cleared_date"] += 1
                continue
            try:
                value_date = datetime.fromisoformat(row.value) if isinstance(row.value, str) else None
                if value_date is None or value_date.tzinfo is None or utc(value_date) != utc(row.effective_at):
                    raise ValueError("Inconsistent event date")
            except (ValueError, TypeError, OverflowError):
                diagnostics["invalid_or_inconsistent_date"] += 1
                continue
            effective = utc(row.effective_at)
            if effective < start or effective >= end:
                diagnostics["outside_window"] += 1
                continue
            index = (effective - start) // duration
            window = windows[index]
            window["observed_records"] += 1
            if len(window["evidence_observation_ids"]) < EVIDENCE_SAMPLE_SIZE:
                window["evidence_observation_ids"].append(row.id)
        diagnostics["ambiguous_latest_records"] = len(ambiguous)
        diagnostics["latest_source_records"] = len({key for _, key in source_rows})
        baseline_total = sum(window["observed_records"] for window in windows[:-1])
        status = "needs_coverage_review"
        if baseline_total < request.minimum_baseline_records:
            status = "insufficient_observed_sample"
        if ambiguous:
            status = "ambiguous_latest_observation"
        result["sources"].append(dict(
            source_id=pin.source_id, methodology_version=pin.methodology_version,
            status=status, windows=windows,
            baseline_mean_observed_records=baseline_total / request.baseline_periods,
            diagnostics=dict(diagnostics),
            evidence_fingerprint=fingerprint([(row.id, row.content_hash) for row, _ in source_rows]),
        ))
    return result
