"""Development Velocity v0 — pure, cutoff-safe signal layered on activity_baseline.

The ONLY data path is ``activity_baseline()``; this module performs no network I/O,
calls no LLM, and mutates nothing. It consumes the counting layer's cutoff-safe,
correction-aware, de-duplicated per-window counts and adds a trailing-mean baseline,
a normalized (z-like) change measure, an explicit abstention rule, a bounded
research score, and a signal object. It never re-counts.

Every edge is an explicit status, never a fabricated 0 or infinity. The score is an
UNVALIDATED research output (``score_is_validated`` is always ``False``) and is
dropped entirely whenever the signal abstains.
"""
from __future__ import annotations

import math

from sqlalchemy.orm import Session

from app.schemas.development_velocity import DevelopmentVelocityRequest
from app.services.activity_baseline import activity_baseline
from app.services.temporal_service import fingerprint, utc
from app.utils.org_scope import get_org_id

METHOD_VERSION = "development-velocity-v0"
SCORE_METHOD_VERSION = "development-velocity-score-v0"
SEASONAL_MIN_MONTHS = 24
Z_CLAMP = 5.0
POINTS_PER_SD = 10.0

SCORE_WARNING = (
    "The 0-100 score is an unvalidated research output pending P2 evaluation; "
    "it has no empirical calibration and is not comparable across markets."
)
SEASONAL_WARNING = (
    "Seasonal adjustment is off: this is a raw trailing comparison and is not "
    "seasonally controlled (Columbus lacks the comparable history to justify it)."
)
JURISDICTION_WARNING = (
    "Market is the issuing City of Columbus jurisdiction only, not the metro or a "
    "utility service area."
)


def _name(value: object) -> str:
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def _baseline_stats(window_counts: list[int], baseline_periods: int) -> tuple[float, float | None, int, int]:
    """Return (mean, sample std with n-1 divisor, total, populated-window count).

    Pure function of the integer baseline counts, so it is deterministic. The
    denominator for the mean is ``baseline_periods`` (not the number of populated
    windows), matching ``activity_baseline``'s documented mean verbatim.
    """
    total = sum(window_counts)
    populated = sum(1 for count in window_counts if count > 0)
    mean = total / baseline_periods
    if baseline_periods < 2:
        return mean, None, total, populated
    variance = sum((count - mean) ** 2 for count in window_counts) / (baseline_periods - 1)
    return mean, math.sqrt(variance), total, populated


def _source_score(z: float | None) -> float | None:
    """50 + POINTS_PER_SD * clamp(z, ±Z_CLAMP), clamped to [0, 100]; None if z is None.

    50 == "at baseline"; each baseline standard deviation is ~10 points. The clamp
    keeps the score bounded and avoids runaway values from a thin baseline.
    """
    if z is None:
        return None
    clamped = max(-Z_CLAMP, min(Z_CLAMP, z))
    return max(0.0, min(100.0, 50.0 + POINTS_PER_SD * clamped))


def _change(
    upstream_status: str,
    current: int,
    mean: float,
    std: float | None,
    baseline_total: int,
    populated: int,
    request: DevelopmentVelocityRequest,
) -> dict:
    """delta / percent_change / z / source_score / per-source status, every edge explicit.

    Priority (mirrors the design §4 table and the ``numeric_change`` contract):
    ambiguous-upstream > zero_baseline > sample-floor abstention > zero_variance >
    calculated. Numeric fields are ``None`` wherever they cannot be honestly derived;
    never a substituted 0 or infinity.
    """
    out = dict(
        status="", delta=None, percent_change=None, z=None,
        source_score=None, baseline_std=std,
    )
    if upstream_status == "ambiguous_latest_observation":
        out["status"] = "ambiguous_latest_observation"
        return out

    delta = float(current) - mean
    if mean == 0:
        # Empty baseline history is a distinct state, not thin-sample abstention and
        # not economic acceleration. percent_change/z are undefined (no divisor).
        out.update(status="zero_baseline", delta=delta)
        return out

    min_records = request.baseline.minimum_baseline_records
    min_windows = request.minimum_populated_baseline_windows
    if baseline_total < min_records or populated < min_windows:
        # Guards against a single spike over a near-empty history reading as a huge z.
        out["status"] = "abstained_insufficient_sample"
        return out

    percent_change = 100.0 * delta / mean
    if std == 0:
        # All baseline windows equal: no dispersion to standardize against.
        out.update(status="zero_variance_baseline", delta=delta, percent_change=percent_change)
        return out

    z = delta / std
    out.update(
        status="calculated", delta=delta, percent_change=percent_change,
        z=z, source_score=_source_score(z),
    )
    return out


def _what_changed(attribute: str, baseline_periods: int, calculated: list[dict], score: float | None) -> str | None:
    """Deterministic templated summary (no LLM). None when abstaining."""
    if not calculated:
        return None
    parts = []
    for source in calculated:
        parts.append(
            f"{source['source_id']} current-window count {source['current']} vs "
            f"trailing {baseline_periods}-window mean {source['baseline_mean']:.1f} "
            f"(delta {source['delta']:+.1f}, z {source['z']:+.1f})"
        )
    return f"Columbus {attribute} {'; '.join(parts)}; score {score} (unvalidated)."


def _confidence(sources: list[dict], seasonal_off: bool) -> tuple[str, str]:
    """(level, rationale) from sample adequacy and coverage flags — never from score."""
    calculated = [source for source in sources if source["status"] == "calculated"]
    if not calculated:
        return "low", (
            "No source produced a standardizable change at this cutoff; the baseline "
            "sample floor was not met."
        )
    total = len(sources)
    ambiguous = sum(1 for source in sources if source["status"] == "ambiguous_latest_observation")
    coverage = sum(
        1 for source in sources
        if source["status"] in {"zero_baseline", "zero_variance_baseline", "abstained_insufficient_sample"}
    )
    clean = len(calculated) == total and ambiguous == 0 and coverage == 0
    level = "medium" if clean else "low"
    rationale = (
        f"{len(calculated)} of {total} sources standardizable"
        f"{f'; {ambiguous} ambiguous-latest' if ambiguous else ''}"
        f"{f'; {coverage} with coverage/zero-baseline diagnostics' if coverage else ''}."
    )
    if seasonal_off:
        rationale += " Seasonal adjustment is off, so confidence is capped below high."
    return level, rationale


def _invalidation_conditions(sources: list[dict]) -> list[str]:
    conditions = [
        "A later correction clears or moves a current-window filing, lowering the current count.",
        "The source cohort methodology version is re-pinned, changing baseline and current counts.",
        "The baseline falls below the minimum sample at a new cutoff, forcing abstention.",
        "A reporting-lag revision moves the current-window boundary.",
    ]
    if any(source["status"] == "ambiguous_latest_observation" for source in sources):
        conditions.append(
            "An ambiguous latest observation appears in the cohort, withdrawing a source from the score."
        )
    return conditions


def develop_velocity(db: Session, request: DevelopmentVelocityRequest) -> dict:
    """Pure, cutoff-safe Development Velocity v0 over a pinned Columbus cohort.

    Calls ``activity_baseline()`` exactly once; never fetches, never calls an LLM,
    never mutates. Returns the signal object as a dict (validated by the route's
    ``response_model``).
    """
    baseline_request = request.baseline
    # activity_baseline enforces cutoff safety, future-as_of rejection (ValueError),
    # and unknown/foreign cohort rejection (LookupError) — inherited unchanged.
    report = activity_baseline(db, baseline_request)

    org_id = get_org_id()
    as_of = utc(baseline_request.as_of)
    pins = sorted(baseline_request.sources, key=lambda pin: pin.source_id)
    canonical_baseline = baseline_request.model_dump(mode="json")
    canonical_baseline.update(
        as_of=as_of.isoformat(), city=_name(baseline_request.city),
        sources=[pin.model_dump() for pin in pins],
    )
    canonical_request = dict(
        baseline=canonical_baseline,
        minimum_populated_baseline_windows=request.minimum_populated_baseline_windows,
        seasonal_adjustment=request.seasonal_adjustment,
    )
    request_fingerprint = fingerprint(
        [org_id, METHOD_VERSION, SCORE_METHOD_VERSION, canonical_request]
    )

    warnings = list(report["warnings"]) + [SCORE_WARNING, SEASONAL_WARNING, JURISDICTION_WARNING]
    common = dict(
        method_id=METHOD_VERSION, schema_version="1",
        request_fingerprint=request_fingerprint, as_of=as_of,
        city=baseline_request.city, state=baseline_request.state,
        attribute=baseline_request.attribute, period_days=baseline_request.period_days,
        baseline_periods=baseline_request.baseline_periods,
        reporting_lag_days=baseline_request.reporting_lag_days,
        score_is_validated=False, seasonal_adjustment_applied=False,
    )

    if report["status"] == "bounded_query_exceeded":
        return dict(
            **common, status="bounded_query_exceeded", what_changed=None, score=None,
            confidence="low",
            confidence_rationale="Cohort exceeded the counting-layer row bound; no counts were computed.",
            sources=[], cited_driver_observation_ids=[],
            invalidation_conditions=_invalidation_conditions([]),
            unavailable_fields=[
                "score (bounded_query_exceeded)",
                "seasonal_adjustment (insufficient comparable history)",
            ],
            warnings=warnings,
        )

    baseline_periods = baseline_request.baseline_periods
    sources: list[dict] = []
    for source in report["sources"]:
        windows = source["windows"]
        counts = [window["observed_records"] for window in windows[:-1]]
        current = windows[-1]["observed_records"]
        mean, std, total, populated = _baseline_stats(counts, baseline_periods)
        change = _change(source["status"], current, mean, std, total, populated, request)
        sources.append(dict(
            source_id=source["source_id"], methodology_version=source["methodology_version"],
            status=change["status"], windows=windows, baseline_mean=mean,
            baseline_std=change["baseline_std"], baseline_total=total,
            populated_baseline_windows=populated, current=current,
            delta=change["delta"], percent_change=change["percent_change"], z=change["z"],
            source_score=change["source_score"], evidence_fingerprint=source["evidence_fingerprint"],
        ))

    standardizable = [source for source in sources if source["source_score"] is not None]
    if standardizable:
        score = round(sum(source["source_score"] for source in standardizable) / len(standardizable), 1)
        status = "calculated"
    else:
        score = None
        status = "abstained_insufficient_sample"

    confidence, confidence_rationale = _confidence(sources, seasonal_off=True)

    cited: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for window in source["windows"]:
            for observation_id in window["evidence_observation_ids"]:
                if observation_id not in seen:
                    seen.add(observation_id)
                    cited.append(observation_id)

    unavailable: list[str] = []
    if any(source["status"] == "zero_baseline" for source in sources):
        unavailable += ["percent_change (zero_baseline)", "z (zero_baseline)"]
    if any(source["status"] == "zero_variance_baseline" for source in sources):
        unavailable.append("z (zero_variance_baseline)")
    if score is None:
        unavailable.append("score (abstained_insufficient_sample)")
    unavailable.append("seasonal_adjustment (insufficient comparable history)")
    deduped: list[str] = []
    for field in unavailable:
        if field not in deduped:
            deduped.append(field)

    return dict(
        **common, status=status,
        what_changed=_what_changed(baseline_request.attribute, baseline_periods, standardizable, score),
        score=score, confidence=confidence, confidence_rationale=confidence_rationale,
        sources=sources, cited_driver_observation_ids=cited,
        invalidation_conditions=_invalidation_conditions(sources),
        unavailable_fields=deduped, warnings=warnings,
    )
