"""Measures whether a pinned historical corpus can meet the predeclared P2.2
Development Velocity evaluation requirements (roadmap P0.8).

This is a MEASURING tool only. It never claims a corpus qualifies on its own
authority, never ingests or fetches anything, and reads the corpus strictly
through the cutoff-safe temporal readers (``observations_as_of`` /
``activity_baseline`` eligibility: ``first_observed_at`` / ``recorded_at`` /
``received_at`` <= ``as_of`` and the latest interpretation known as-of the
cutoff). Depth is never fabricated: when evidence is absent the depth fields are
zero/None and the verdict is an ``insufficient_*`` HOLD.

The predeclared requirements live in
``docs/signals/2026-10-20-development-velocity-v0-evaluation-protocol.md`` and
``eval/replay/fixtures/dv_v0_evaluation_protocol.json``. Passing here is a
prerequisite gate; it is not source activation, commercial-reuse clearance, or a
validation of the (still UNVALIDATED) development-velocity-v0 score.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ingestion import IngestionSource
from app.schemas.activity_baseline import SourceCohort
from app.schemas.temporal import NonblankKey, UtcCutoff
from app.services.temporal_service import fingerprint, observations_as_of, utc
from app.utils.org_scope import get_org_id

METHODOLOGY_VERSION = "corpus-qualification-v0"
PAGE_SIZE = 500
MAX_OFFSET = 10000  # observations_as_of rejects offset > 10000.

WARNINGS = [
    "Qualification measures the corpus only; it is not source activation, commercial-reuse clearance, or score validation.",
    "Depth is read through the cutoff-safe temporal path; backfilled history not known as-of the cutoff is excluded.",
    "Counts describe latest-interpretation source records, not verified unique projects; overlapping sources are not summed.",
    "Event-date completeness and duplicate rate are honest measurements, not a guarantee of source-latency or identity resolution.",
    "Meeting the predeclared floors is necessary, not sufficient: it permits a measured evaluation, never an automatic pass.",
    "Inconclusive or below-floor corpora return insufficient_* (HOLD); no predictive claim is made.",
]


class CorpusQualificationRequest(BaseModel):
    """A pinned cohort plus the predeclared P2.2 floors to measure against.

    The floors default to the predeclared protocol values so a real call fixes
    the same thresholds; they are carried in the request so they flow into the
    reproducible request fingerprint.
    """

    model_config = ConfigDict(extra="forbid")

    as_of: UtcCutoff
    sources: list[SourceCohort] = Field(min_length=1, max_length=10)
    city: NonblankKey
    state: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{2}$")]
    attribute: Literal["permit.filed_at", "permit.issued_at"] = "permit.filed_at"
    stage_attribute: NonblankKey | None = "permit.approval_stage"
    # Predeclared protocol values (dv-v0-evaluation-protocol-2026-10-20).
    window_days: int = Field(default=30, ge=7, le=90)
    horizon_windows: int = Field(default=3, ge=1, le=12)
    baseline_periods: int = Field(default=6, ge=3, le=12)
    holdout_windows: int = Field(default=6, ge=0, le=24)
    min_fired_signals: int = Field(default=5, ge=1, le=1000)
    min_evaluable_periods: int = Field(default=12, ge=1, le=1000)
    reporting_lag_days: int = Field(default=7, ge=0, le=60)
    required_event_date_completeness: float = Field(default=0.95, ge=0.0, le=1.0)
    max_duplicate_project_rate: float = Field(default=0.10, ge=0.0, le=1.0)
    max_month_gaps: int = Field(default=0, ge=0, le=60)

    @model_validator(mode="after")
    def unique_sources(self):
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("Pin exactly one methodology version per source")
        return self


def _name(value: object) -> str:
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def _event_date(obs) -> datetime | None:
    """Return the valid, self-consistent event date, else None (collection-only)."""
    if obs.value is None or obs.effective_at is None:
        return None
    try:
        value_date = datetime.fromisoformat(obs.value) if isinstance(obs.value, str) else None
        if value_date is None or value_date.tzinfo is None:
            return None
        if utc(value_date) != utc(obs.effective_at):
            return None
        return utc(obs.effective_at)
    except (ValueError, TypeError, OverflowError):
        return None


def _scan_latest(db: Session, *, as_of: datetime, attribute: str, source_ids: set[str]) -> tuple[dict, bool]:
    """Page the cutoff-safe reader and keep the latest interpretation per series.

    observations_as_of orders by recorded_at desc, id desc, so the first row seen
    for a series_key is its latest known interpretation as-of the cutoff.
    """
    latest: dict[str, object] = {}
    offset = 0
    overflow = False
    while True:
        rows = observations_as_of(db, as_of=as_of, attribute=attribute, limit=PAGE_SIZE, offset=offset)
        for obs in rows:
            if obs.source_type == "permit" and obs.source_id in source_ids:
                latest.setdefault(obs.series_key, obs)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        if offset > MAX_OFFSET:
            overflow = True
            break
    return latest, overflow


def _classify_cohort(latest: dict, request: CorpusQualificationRequest) -> tuple[list, Counter]:
    """Keep org+geography-matched records; tally geography diagnostics."""
    city, state = _name(request.city), _name(request.state)
    cohort: list[tuple[object, datetime | None]] = []
    diagnostics: Counter = Counter()
    for obs in latest.values():
        geo = obs.geography if isinstance(obs.geography, dict) else {}
        if not _name(geo.get("city")) or not _name(geo.get("state")):
            diagnostics["missing_geography"] += 1
            continue
        if _name(geo["city"]) != city or _name(geo["state"]) != state:
            diagnostics["outside_geography"] += 1
            continue
        event = _event_date(obs)
        if obs.value is not None and obs.effective_at is not None and event is None:
            diagnostics["invalid_or_inconsistent_date"] += 1
        cohort.append((obs, event))
    return cohort, diagnostics


def _recorded_depth(cohort: list) -> dict:
    recorded = [utc(obs.recorded_at) for obs, _ in cohort if obs.recorded_at is not None]
    if not recorded:
        return {"earliest_recorded_at": None, "latest_recorded_at": None, "recorded_span_days": None}
    earliest, latest = min(recorded), max(recorded)
    return {
        "earliest_recorded_at": earliest.isoformat(),
        "latest_recorded_at": latest.isoformat(),
        "recorded_span_days": (latest - earliest).days,
    }


def qualify_corpus(db: Session, request: CorpusQualificationRequest) -> dict:
    """Measure a pinned Columbus cohort against the predeclared P2.2 floors."""
    try:
        as_of = utc(request.as_of)
    except OverflowError as exc:
        raise ValueError("as_of exceeds the supported UTC date range") from exc
    if as_of > datetime.now(timezone.utc):
        raise ValueError("as_of cannot be in the future")

    org_id = get_org_id()
    pins = sorted(request.sources, key=lambda pin: pin.source_id)
    source_ids = {pin.source_id for pin in pins}
    available = set(db.scalars(select(IngestionSource.id).where(
        IngestionSource.organization_id == org_id,
        IngestionSource.id.in_(source_ids),
    )))
    if available != source_ids:
        raise LookupError("Source cohort not found")

    canonical_request = request.model_dump(mode="json")
    canonical_request.update(
        as_of=as_of.isoformat(), city=_name(request.city),
        sources=[pin.model_dump() for pin in pins],
    )
    duration = timedelta(days=request.window_days)
    minimums = {
        "min_fired_signals": request.min_fired_signals,
        "min_evaluable_periods": request.min_evaluable_periods,
        "horizon_windows": request.horizon_windows,
        "window_days": request.window_days,
        "baseline_periods": request.baseline_periods,
        "holdout_windows": request.holdout_windows,
        "required_event_date_completeness": request.required_event_date_completeness,
        "max_duplicate_project_rate": request.max_duplicate_project_rate,
        "max_month_gaps": request.max_month_gaps,
    }
    result: dict = {
        "methodology_version": METHODOLOGY_VERSION,
        "request_fingerprint": fingerprint([org_id, METHODOLOGY_VERSION, canonical_request]),
        "as_of": as_of.isoformat(),
        "market": {"city": request.city, "state": request.state},
        "attribute": request.attribute,
        "predeclared_minimums": minimums,
        "warnings": list(WARNINGS),
    }

    latest, overflow = _scan_latest(db, as_of=as_of, attribute=request.attribute, source_ids=source_ids)
    cohort, diagnostics = _classify_cohort(latest, request)
    diagnostics["sources_pinned"] = len(pins)

    # Stage counts are a parallel cutoff-safe read; absence is reported, not faked.
    per_stage: dict[str, int] = {}
    stage_records = 0
    if request.stage_attribute:
        stage_latest, stage_overflow = _scan_latest(
            db, as_of=as_of, attribute=request.stage_attribute, source_ids=source_ids,
        )
        overflow = overflow or stage_overflow
        stage_cohort, _ = _classify_cohort(stage_latest, request)
        stage_counter: Counter = Counter()
        for obs, _ in stage_cohort:
            stage_records += 1
            label = obs.value if isinstance(obs.value, str) and obs.value.strip() else "unknown"
            stage_counter[label] += 1
        per_stage = dict(sorted(stage_counter.items()))

    event_dates = sorted(event for _, event in cohort if event is not None)
    event_present = len(event_dates)
    cohort_records = len(cohort)
    collection_only = cohort_records - event_present

    # Depth: complete 30-day windows and evaluable monthly periods.
    if event_dates:
        earliest, latest_event = event_dates[0], event_dates[-1]
        span = latest_event - earliest
        complete_windows = int(span // duration)
    else:
        earliest = latest_event = None
        complete_windows = 0
    evaluable_periods = max(0, complete_windows - request.horizon_windows - request.baseline_periods)
    holdout_evaluable = min(evaluable_periods, request.holdout_windows)
    in_sample_evaluable = max(0, evaluable_periods - request.holdout_windows)

    # Month gaps/missingness across the complete windows only.
    window_hits: set[int] = set()
    if earliest is not None and complete_windows > 0:
        for event in event_dates:
            index = int((event - earliest) // duration)
            if 0 <= index < complete_windows:
                window_hits.add(index)
    gap_indices = sorted(set(range(complete_windows)) - window_hits)
    month_gaps = len(gap_indices)

    # Duplicate-project rate: records beyond the first per graph entity (project).
    by_entity: dict[str, int] = defaultdict(int)
    for obs, _ in cohort:
        by_entity[obs.entity_id] += 1
    distinct_projects = len(by_entity)
    duplicate_records = sum(count - 1 for count in by_entity.values())
    duplicate_rate = round(duplicate_records / cohort_records, 6) if cohort_records else 0.0
    date_completeness = round(event_present / cohort_records, 6) if cohort_records else 0.0

    result["time_depth"] = {
        "earliest_event_date": earliest.isoformat() if earliest else None,
        "latest_event_date": latest_event.isoformat() if latest_event else None,
        "event_span_days": (latest_event - earliest).days if earliest and latest_event else None,
        "complete_windows": complete_windows,
        "evaluable_periods": evaluable_periods,
        "in_sample_evaluable_periods": in_sample_evaluable,
        "holdout_evaluable_periods": holdout_evaluable,
        "max_possible_fired_signals": evaluable_periods,
        "recorded_time_depth": _recorded_depth(cohort),
    }
    result["completeness"] = {
        "cohort_records": cohort_records,
        "event_date_present": event_present,
        "collection_only": collection_only,
        "event_date_completeness": date_completeness,
        "distinct_projects": distinct_projects,
        "duplicate_records": duplicate_records,
        "duplicate_project_rate": duplicate_rate,
        "month_gaps": month_gaps,
        "gap_window_indices": gap_indices,
    }
    result["per_stage_counts"] = per_stage
    result["diagnostics"] = {
        **{key: diagnostics[key] for key in sorted(diagnostics)},
        "stage_records": stage_records,
        "stage_attribute": request.stage_attribute,
        "scan_overflow": overflow,
    }

    # Verdict vs the predeclared floors. Depth (can the evaluation even run?) is
    # gated first; completeness is gated only once there is depth to trust.
    depth_shortfall: list[str] = []
    completeness_shortfall: list[str] = []
    if overflow:
        completeness_shortfall.append("cohort exceeds the scan bound; narrow the pinned sources before qualifying")
    if evaluable_periods < request.min_evaluable_periods:
        depth_shortfall.append(f"{evaluable_periods} evaluable periods vs {request.min_evaluable_periods} required")
    if evaluable_periods < request.min_fired_signals:
        depth_shortfall.append(
            f"{evaluable_periods} max possible fired signals vs {request.min_fired_signals} required"
        )
    if cohort_records == 0:
        completeness_shortfall.append("no eligible records in the pinned cohort as-of the cutoff")
    else:
        if date_completeness < request.required_event_date_completeness:
            completeness_shortfall.append(
                f"event-date completeness {date_completeness} vs {request.required_event_date_completeness} required"
            )
        if duplicate_rate > request.max_duplicate_project_rate:
            completeness_shortfall.append(
                f"duplicate-project rate {duplicate_rate} vs {request.max_duplicate_project_rate} ceiling"
            )
        if month_gaps > request.max_month_gaps:
            completeness_shortfall.append(f"{month_gaps} month gaps vs {request.max_month_gaps} allowed")

    if depth_shortfall:
        verdict, shortfall = "insufficient_depth", depth_shortfall
    elif completeness_shortfall:
        verdict, shortfall = "insufficient_completeness", completeness_shortfall
    else:
        verdict, shortfall = "ready", []

    result["status"] = (
        "bounded_query_exceeded" if overflow
        else "no_eligible_records" if cohort_records == 0
        else "measured"
    )
    result["verdict"] = verdict
    result["shortfall"] = shortfall
    return result
