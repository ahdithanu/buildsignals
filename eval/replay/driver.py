"""Cutoff-safe replay driver.

For a method id + version and a sequence of cutoffs ``T``, produce the signal
as-of each ``T`` using only eligible observations, deterministically and
reproducibly. The method is injected through a registry so the driver stays
domain-neutral like ``temporal_service``; the only time input a method ever sees
is ``as_of``, and every read goes through
``observations_as_of`` / ``events_as_of`` / ``numeric_change`` at ``as_of=T``.

A reference fixture method is registered now so the harness is testable before
Development Velocity v0 (P1.2) lands; that signal will register itself here by
id + version without any change to this driver.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping, Protocol, Sequence

from sqlalchemy import event
from sqlalchemy.orm import Session

import app.services.temporal_service as temporal
from app.schemas.activity_baseline import ActivityBaselineRequest
from app.services.activity_baseline import activity_baseline
from app.services.temporal_service import fingerprint, numeric_change, observations_as_of, utc
from eval.replay.manifest import ReplayManifest, SeriesSpec, verify

# Signal statuses the driver copies through verbatim. "unavailable" and
# "insufficient_history" mean the data to decide did not exist at T; the driver
# never fabricates a zero, an interpolation, or a carried-forward value.
STATUSES = ("fired", "no_signal", "unavailable", "insufficient_history")
MODES = ("known_then", "reconstructed")


class ClockAccessError(RuntimeError):
    """Raised when a method reads the wall clock during replay."""


class ReplayWriteError(RuntimeError):
    """Raised when a method attempts a write during replay."""


@dataclass(frozen=True)
class SignalOutput:
    """Concrete ``SignalResult``: a method-defined decision plus its lineage."""

    status: str
    value: float | None
    drivers: list[dict]
    method_version: str


class SignalFn(Protocol):
    def __call__(
        self, db: Session, *, as_of: datetime, series: SeriesSpec, method_version: str,
    ) -> SignalOutput: ...


@dataclass(frozen=True)
class MethodEntry:
    fn: SignalFn
    versions: frozenset[str]


REGISTRY: dict[str, MethodEntry] = {}


def register(method_id: str, versions: Sequence[str], fn: SignalFn) -> None:
    REGISTRY[method_id] = MethodEntry(fn=fn, versions=frozenset(versions))


def get_method(method_id: str, method_version: str) -> SignalFn:
    """Resolve a method; a missing id or version is a hard error, never a fallback."""
    entry = REGISTRY.get(method_id)
    if entry is None:
        raise KeyError(f"Unknown method id: {method_id!r}")
    if method_version not in entry.versions:
        raise ValueError(
            f"Method {method_id!r} does not support version {method_version!r}",
        )
    return entry.fn


# ── Reference fixture method ────────────────────────────────────────────────

REFERENCE_METHOD_ID = "devvelocity-reference"
REFERENCE_METHOD_VERSION = "devvelocity-ref-v0"
# Method-internal firing rule, pinned to the method version (not tunable from
# the predeclared thresholds file, which carries only P2.2 placeholders).
REFERENCE_FIRE_THRESHOLD_PCT = 25.0


def reference_signal(
    db: Session, *, as_of: datetime, series: SeriesSpec, method_version: str,
) -> SignalOutput:
    """Trivial ``numeric_change``-based signal standing in for Development Velocity v0.

    Fires when the latest eligible step change for the (single) series is an
    increase of at least ``REFERENCE_FIRE_THRESHOLD_PCT`` percent. Reads nothing
    but ``numeric_change`` at ``as_of=T``.
    """
    if method_version != REFERENCE_METHOD_VERSION:
        raise ValueError(f"Unsupported reference version: {method_version!r}")
    if not series.series_keys:
        return SignalOutput("insufficient_history", None, [], method_version)
    change = numeric_change(db, series_key=series.series_keys[0], as_of=as_of)
    drivers: list[dict] = []
    if change["current_observation_id"] is not None:
        drivers.append({"observation_id": change["current_observation_id"], "role": "current"})
    if change["previous_observation_id"] is not None:
        drivers.append({"observation_id": change["previous_observation_id"], "role": "previous"})

    status = change["status"]
    if status == "insufficient_history":
        return SignalOutput("insufficient_history", None, drivers, method_version)
    if status in ("non_numeric", "incompatible_units", "numeric_overflow"):
        return SignalOutput("unavailable", None, drivers, method_version)
    percent = change["percent_change"]
    fired = (
        change["direction"] == "up"
        and percent is not None
        and percent >= REFERENCE_FIRE_THRESHOLD_PCT
    )
    return SignalOutput("fired" if fired else "no_signal", percent, drivers, method_version)


register(REFERENCE_METHOD_ID, [REFERENCE_METHOD_VERSION], reference_signal)


# ── Determinism guards ──────────────────────────────────────────────────────

@contextlib.contextmanager
def _replay_guards(db: Session):
    """Block the wall clock and any write for the duration of a method call.

    - ``temporal._utcnow`` is patched to raise, so a method that reads the real
      clock fails the run loudly (the eligibility readers take ``as_of``
      explicitly and never call it).
    - a ``before_flush`` listener raises if a method leaves pending writes, so a
      buggy method cannot mutate the frozen snapshot mid-run (the ORM already
      rejects temporal update/delete; this also blocks inserts).
    """
    original = temporal._utcnow

    def _blocked_clock() -> datetime:
        raise ClockAccessError("Replay methods must not read the wall clock")

    def _blocked_flush(session: Session, _flush_context: object, _instances: object) -> None:
        if session.new or session.dirty or session.deleted:
            raise ReplayWriteError("Replay is read-only; a method attempted a write")

    temporal._utcnow = _blocked_clock
    event.listen(db, "before_flush", _blocked_flush)
    try:
        yield
    finally:
        temporal._utcnow = original
        event.remove(db, "before_flush", _blocked_flush)


# ── Driver results ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CutoffSignal:
    as_of: datetime
    status: str
    value: float | None
    drivers: list[dict]
    fingerprint: str
    mode: str

    def canonical(self) -> dict:
        return {
            "as_of": utc(self.as_of).isoformat(),
            "status": self.status,
            "value": self.value,
            "drivers": sorted(
                [dict(driver) for driver in self.drivers],
                key=lambda driver: (driver.get("role", ""), driver.get("observation_id") or ""),
            ),
            "mode": self.mode,
        }


@dataclass(frozen=True)
class ReplayRun:
    manifest: ReplayManifest
    signals: tuple[CutoffSignal, ...]
    run_fingerprint: str

    def canonical(self) -> dict:
        return {
            "manifest": self.manifest.canonical(),
            "signals": [signal.canonical() for signal in self.signals],
        }


def _signal_fingerprint(as_of: datetime, result: SignalOutput, mode: str) -> str:
    return fingerprint({
        "as_of": utc(as_of).isoformat(),
        "status": result.status,
        "value": result.value,
        "method_version": result.method_version,
        "drivers": sorted(
            [dict(driver) for driver in result.drivers],
            key=lambda driver: (driver.get("role", ""), driver.get("observation_id") or ""),
        ),
        "mode": mode,
    })


def _classify_mode(
    db: Session, *, as_of: datetime, result: SignalOutput, guard: timedelta, org_id: str,
) -> str:
    """known_then if the cited knowledge genuinely predates T by the guard margin."""
    cutoff = utc(as_of) - guard
    latest_recorded: datetime | None = None
    for driver in result.drivers:
        oid = driver.get("observation_id")
        if oid is None:
            continue
        rows = observations_as_of(db, as_of=as_of, observation_id=oid, limit=1)
        for row in rows:
            recorded = utc(row.recorded_at)
            if latest_recorded is None or recorded > latest_recorded:
                latest_recorded = recorded
    if latest_recorded is None:
        return "known_then"
    return "known_then" if latest_recorded <= cutoff else "reconstructed"


def replay(
    db: Session, *, method_id: str, method_version: str,
    cutoffs: Sequence[datetime], series: SeriesSpec, manifest: ReplayManifest,
) -> ReplayRun:
    """Produce the signal as-of each cutoff, cutoff-safe and reproducibly."""
    if manifest.method_id != method_id or manifest.method_version != method_version:
        raise ValueError("Manifest method/version does not match the requested run")
    if series.canonical() != manifest.series.canonical():
        raise ValueError("Manifest series does not match the requested run")
    if _normalize(cutoffs) != manifest.cutoffs:
        raise ValueError("Manifest cutoffs do not match the requested run")
    verify(db, manifest)
    method = get_method(method_id, method_version)

    ordered = _normalize(cutoffs)
    signals: list[CutoffSignal] = []
    for as_of in ordered:
        with _replay_guards(db):
            result = method(db, as_of=as_of, series=series, method_version=method_version)
            if result.status not in STATUSES:
                raise ValueError(f"Method returned unsupported status: {result.status!r}")
            mode = _classify_mode(
                db, as_of=as_of, result=result,
                guard=manifest.reconstruction_guard, org_id=manifest.org_id,
            )
        signals.append(CutoffSignal(
            as_of=as_of, status=result.status, value=result.value,
            drivers=[dict(driver) for driver in result.drivers],
            fingerprint=_signal_fingerprint(as_of, result, mode), mode=mode,
        ))

    run_fingerprint = fingerprint({
        "manifest": manifest.canonical(),
        "signals": [signal.canonical() for signal in signals],
    })
    return ReplayRun(manifest=manifest, signals=tuple(signals), run_fingerprint=run_fingerprint)


def _normalize(cutoffs: Sequence[datetime]) -> tuple[datetime, ...]:
    if not cutoffs:
        raise ValueError("At least one cutoff is required")
    normalized = []
    for cutoff in cutoffs:
        if cutoff.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        normalized.append(utc(cutoff))
    return tuple(sorted(set(normalized)))


# ── Trailing baseline, run cutoff-safe through the same cutoffs ─────────────

@dataclass(frozen=True)
class BaselineCrossing:
    as_of: datetime
    crossed: bool


@dataclass(frozen=True)
class BaselineRun:
    """The ``activity_baseline`` trailing comparator evaluated as-of each cutoff."""

    crossings: tuple[BaselineCrossing, ...]
    move: float
    params: Mapping[str, Any] = field(default_factory=dict)

    def first_cross(self) -> datetime | None:
        for crossing in self.crossings:
            if crossing.crossed:
                return crossing.as_of
        return None


def _baseline_crossed(result: dict, move: float) -> bool:
    """A source crosses when its current window exceeds move * baseline mean."""
    for source in result.get("sources", []):
        windows = source.get("windows", [])
        current = next((w for w in windows if w["role"] == "current"), None)
        mean = source.get("baseline_mean_observed_records", 0) or 0
        if current is None or mean <= 0:
            continue
        if current["observed_records"] >= move * mean:
            return True
    return False


def baseline_run(
    db: Session, *, cutoffs: Sequence[datetime], request_params: Mapping[str, Any],
    move: float,
) -> BaselineRun:
    """Run ``activity_baseline`` as-of each cutoff; it is already cutoff-safe.

    ``activity_baseline`` filters strictly on ``first_observed_at``/
    ``recorded_at``/``received_at`` <= ``as_of``, so each crossing reflects only
    evidence known at that cutoff - the baseline is a cutoff-safe comparator too.
    """
    ordered = _normalize(cutoffs)
    crossings: list[BaselineCrossing] = []
    for as_of in ordered:
        request = ActivityBaselineRequest(as_of=as_of, **dict(request_params))
        result = activity_baseline(db, request)
        crossings.append(BaselineCrossing(as_of=as_of, crossed=_baseline_crossed(result, move)))
    return BaselineRun(crossings=tuple(crossings), move=move, params=dict(request_params))
