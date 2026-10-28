"""Read-only P0.8 receipts bound to actual replay evidence and protocol content.

Digests provide integrity, not authentication. Independent coverage attestations
retain the operator trust model of qualify_corpus; a digest is not an audit.
The verifier never trusts a caller's ready/verified boolean: it re-reads the DB,
recomputes qualification and requires byte-equivalent canonical receipt content.
"""
from __future__ import annotations

import hmac
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ingestion import RawSourceRecord
from app.models.temporal import TemporalObservation
from app.schemas.activity_baseline import ActivityBaselineRequest
from app.services.corpus_qualification import CorpusQualificationRequest, qualify_corpus
from app.services.temporal_service import fingerprint, utc
from app.utils.org_scope import get_org_id
from eval.replay.manifest import ReplayManifest, verify

BINDING_VERSION = 'replay-corpus-binding-v1'


def _value(protocol, key, default=None):
    value = protocol.get(key, default)
    return value.get('value', default) if isinstance(value, Mapping) else value


def _validate_scope(db: Session, manifest: ReplayManifest,
                    request: CorpusQualificationRequest, protocol: Mapping[str, Any]) -> None:
    if manifest.org_id != get_org_id():
        raise ValueError('Replay organization differs from the active organization')
    verify(db, manifest)
    if (request.coverage_audit is not None
            and request.coverage_audit.attested_snapshot_id != manifest.snapshot_id):
        raise ValueError('Coverage audit does not attest the exact frozen snapshot')
    if protocol.get('method') != manifest.method_id or protocol.get('method_version') != manifest.method_version:
        raise ValueError('Protocol method/version differs from the replay')
    if manifest.method_id != 'development-velocity-v0':
        raise ValueError('Corpus binding currently supports Development Velocity v0 only')
    if not manifest.cutoffs or utc(request.as_of) < max(manifest.cutoffs):
        raise ValueError('Qualification as_of precedes replay cutoffs')
    baseline = ActivityBaselineRequest(as_of=request.as_of, **dict(manifest.series.params['baseline']))
    if (baseline.sources != request.sources or baseline.attribute != request.attribute
            or ' '.join(baseline.city.split()).casefold() != ' '.join(request.city.split()).casefold() or baseline.state != request.state
            or baseline.period_days != request.window_days or baseline.baseline_periods != request.baseline_periods
            or baseline.reporting_lag_days != request.reporting_lag_days
            or manifest.series.methodology_version != request.sources[0].methodology_version):
        raise ValueError('Qualification source/method/geography/windows differ from replay baseline')

    sample = _value(protocol, 'min_sample_size', {})
    sample = sample if isinstance(sample, Mapping) else {}
    required_fired = _value(protocol, 'min_fired_signals', sample.get('min_fired_signals'))
    required_periods = _value(protocol, 'min_evaluable_periods', sample.get('min_evaluable_periods'))
    outcome = _value(protocol, 'outcome_definition', {})
    outcome = outcome if isinstance(outcome, Mapping) else {}
    holdout = _value(protocol, 'holdout_periods', {})
    holdout = holdout if isinstance(holdout, Mapping) else {}
    if required_fired is None or required_periods is None:
        raise ValueError('Protocol must explicitly declare sample floors')
    exact = {
        'min_fired_signals': required_fired, 'min_evaluable_periods': required_periods,
        'window_days': outcome.get('window_days', 30),
        'horizon_windows': outcome.get('horizon_windows_H', 3),
        'holdout_windows': holdout.get('count', 6),
        'baseline_periods': 6, 'reporting_lag_days': 7,
        'required_event_date_completeness': 0.95,
        'max_duplicate_project_rate': 0.10, 'max_month_gaps': 0,
    }
    if any(getattr(request, key) != value for key, value in exact.items()):
        raise ValueError('Qualification floors differ from the predeclared protocol/P0.8 contract')

    # DV reads every matching source/method row, not merely series_keys. Require
    # the frozen cohort to equal its entire reader universe (plus audited stage
    # observations). Never let omitted series influence a replay outside its hash.
    pin = request.sources[0]
    attributes = [request.attribute] + ([request.stage_attribute] if request.stage_attribute else [])
    rows = db.scalars(select(TemporalObservation).where(
        TemporalObservation.organization_id == manifest.org_id,
        TemporalObservation.source_id == pin.source_id,
        TemporalObservation.methodology_version == pin.methodology_version,
        TemporalObservation.attribute.in_(attributes),
    )).all()
    if not rows or {row.series_key for row in rows} != set(manifest.series.series_keys):
        raise ValueError('Frozen series do not exactly cover the full pinned source/method reader universe')
    # The qualifier currently does not join raw receipts. Fail closed if an
    # observation otherwise visible at qualification time has an ineligible or
    # broken raw provenance chain; never let it inflate the qualification gate.
    for row in rows:
        raw = db.get(RawSourceRecord, row.raw_source_record_id)
        if (raw is None or raw.organization_id != manifest.org_id
                or raw.source_id != pin.source_id or raw.record_type != 'permit'):
            raise ValueError('Missing or mismatched raw permit provenance')
        if (utc(row.first_observed_at) <= utc(request.as_of)
                and utc(row.recorded_at) <= utc(request.as_of)
                and utc(raw.received_at) > utc(request.as_of)):
            raise ValueError('Raw receipt is after qualification cutoff')


def produce_corpus_binding(db: Session, *, manifest: ReplayManifest,
                           request: CorpusQualificationRequest,
                           protocol: Mapping[str, Any]) -> dict:
    """Measure actual DB evidence; never accept a caller-provided ready receipt."""
    _validate_scope(db, manifest, request, protocol)
    qualification = qualify_corpus(db, request)
    # verify again: any concurrent mutation of the frozen evidence aborts.
    verify(db, manifest)
    payload = {
        'binding_version': BINDING_VERSION,
        'organization_id': manifest.org_id,
        'manifest_fingerprint': fingerprint(manifest.to_json()),
        'snapshot_id': manifest.snapshot_id,
        'protocol_fingerprint': fingerprint(dict(protocol)),
        'request': request.model_dump(mode='json'),
        'qualification': qualification,
    }
    return {**payload, 'receipt_fingerprint': fingerprint(payload)}


def verify_corpus_binding(db: Session, *, manifest: ReplayManifest,
                          protocol: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict:
    """Recompute evidence and qualification; malformed or stale receipts HOLD."""
    try:
        request = CorpusQualificationRequest.model_validate(receipt['request'])
        fresh = produce_corpus_binding(db, manifest=manifest, request=request, protocol=protocol)
        if not hmac.compare_digest(fingerprint(dict(receipt)), fingerprint(fresh)):
            raise ValueError('Corpus receipt differs from current evidence/protocol/manifest')
        report = fresh['qualification']
        required = protocol.get('preconditions', {}).get('qualified_historical_corpus_P0_8', {}).get('required_request_fingerprint')
        if required is not None and required != report['request_fingerprint']:
            raise ValueError('Qualification request fingerprint differs from protocol')
        qualified = report['verdict'] == 'ready'
        return {'verified': True, 'qualified': qualified, 'echo': fresh,
                'reason': 'P0.8 evidence binding verified' if qualified else f"P0.8 corpus remains {report['verdict']}"}
    except (ValueError, TypeError, KeyError, AttributeError, LookupError) as exc:
        return {'verified': False, 'qualified': False, 'echo': None, 'reason': f'P0.8 binding refused: {exc}'}


def verify_replay_result(db: Session, run) -> None:
    """Re-execute the pinned implementation; caller-computed hashes are insufficient.

    A valid corpus receipt says nothing about supplied signal outputs. Compare
    actual cutoff-safe replay results, including their canonical values, mode,
    evidence and individual/run fingerprints before allowing sample evaluation.
    """
    from eval.replay.driver import get_method, replay
    from eval.replay.dv_signal import development_velocity_signal

    manifest = run.manifest
    if get_method(manifest.method_id, manifest.method_version) is not development_velocity_signal:
        raise ValueError('Replay registry does not resolve to the pinned DV implementation')
    actual = replay(db, method_id=manifest.method_id, method_version=manifest.method_version,
                    cutoffs=manifest.cutoffs, series=manifest.series, manifest=manifest)
    if (actual.canonical() != run.canonical()
            or actual.run_fingerprint != run.run_fingerprint
            or [signal.fingerprint for signal in actual.signals]
            != [signal.fingerprint for signal in run.signals]):
        raise ValueError('Supplied replay result differs from the actual frozen replay')
