"""Synthetic operator-audited evidence only; never certifies real Columbus data."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.models.temporal import TemporalObservation
from app.services.corpus_qualification import CorpusQualificationRequest, qualify_corpus
from eval.replay.corpus_binding import produce_corpus_binding, verify_corpus_binding
from eval.replay.driver import CutoffSignal, replay
from eval.replay.evaluate import verdict
from eval.replay.manifest import SeriesSpec, freeze, load_rows

UTC = timezone.utc
AS_OF = datetime(2026, 1, 1, tzinfo=UTC)
START = datetime(2024, 1, 1, tzinfo=UTC)
PROTOCOL = {
    'method': 'development-velocity-v0', 'method_version': 'development-velocity-v0',
    'min_fired_signals': 5, 'min_evaluable_periods': 12,
    'outcome_threshold': 100, 'min_hit_rate': 0.7, 'false_positive_tolerance': 0.33,
    'preconditions': {'qualified_historical_corpus_P0_8': {}},
}


@pytest.fixture
def bound(db):
    rows = []
    for i in range(22):
        event = START + timedelta(days=30 * i)
        rows.append(dict(key=f'bind-{i}', entity_id=f'entity-{i}', source_key='bind-source',
                         external_record_id=f'permit-{i}', attribute='permit.filed_at',
                         value=event.isoformat(), effective_at=event.isoformat(),
                         first_observed_at=(event + timedelta(days=1)).isoformat(),
                         recorded_at=(event + timedelta(days=2)).isoformat(),
                         methodology_version='permit-v1', record_type='permit',
                         source_type='permit', geography={'city': 'Columbus', 'state': 'OH'}))
    loaded = load_rows(db, rows)
    baseline = dict(sources=[dict(source_id='bind-source', methodology_version='permit-v1')],
                    city='Columbus', state='OH', attribute='permit.filed_at')
    series = SeriesSpec(loaded.series_keys, 'permit-v1', {'baseline': baseline, 'firing_threshold': 70})
    manifest = freeze(db, method_id=PROTOCOL['method'], method_version=PROTOCOL['method_version'],
                      series=series, cutoffs=[AS_OF - timedelta(days=120)], thresholds={},
                      data_scope='local_fixture')
    request = CorpusQualificationRequest(as_of=AS_OF, **baseline, stage_attribute=None)
    report = qualify_corpus(db, request)
    audit = dict(auditor='synthetic-reviewer', attested_at=AS_OF,
                 audit_methodology_version='synthetic-audit-v1', attested_snapshot_id=manifest.snapshot_id,
                 attested_request_fingerprint=report['request_fingerprint'],
                 covered_window_indices=list(range(21)), known_then_availability_confirmed=True,
                 decision='coverage_audited', rationale='Synthetic test evidence only')
    request = request.model_copy(update={'coverage_audit':
        type(request).model_validate({**request.model_dump(), 'coverage_audit': audit}).coverage_audit})
    receipt = produce_corpus_binding(db, manifest=manifest, request=request, protocol=PROTOCOL)
    return manifest, request, receipt


def test_audited_evidence_can_clear_binding_and_reach_sample_metrics(db, bound):
    manifest, _, receipt = bound
    assert verify_corpus_binding(db, manifest=manifest, protocol=PROTOCOL, receipt=receipt)['qualified']
    from eval.replay import dv_signal  # noqa: F401 — register the real method
    run = replay(db, method_id=manifest.method_id, method_version=manifest.method_version,
                 manifest=manifest, series=manifest.series, cutoffs=manifest.cutoffs)
    result = verdict(run, outcomes={manifest.cutoffs[0]: 110}, protocol=PROTOCOL,
                     db=db, corpus_binding=receipt)
    assert result['verdict'] == 'insufficient_sample'


@pytest.mark.parametrize('field,value', [('geography', {'city': 'Other', 'state': 'OH'}),
                                       ('confidence', 0.2), ('source_type', 'other'),
                                       ('entity_id', 'swapped-entity')])
def test_database_mutations_invalidate_receipt(db, bound, field, value):
    manifest, _, receipt = bound
    # Simulate corruption of a local snapshot below the immutable ORM API.
    db.execute(update(TemporalObservation).where(TemporalObservation.id == 'obs-bind-0')
               .values({field: value}), execution_options={'synchronize_session': False})
    db.expire_all()
    assert not verify_corpus_binding(db, manifest=manifest, protocol=PROTOCOL, receipt=receipt)['qualified']


def test_protocol_and_receipt_tampering_fail(db, bound):
    manifest, _, receipt = bound
    assert not verify_corpus_binding(db, manifest=manifest, protocol={**PROTOCOL, 'min_fired_signals': 1}, receipt=receipt)['qualified']
    assert not verify_corpus_binding(db, manifest=manifest, protocol=PROTOCOL, receipt={**receipt, 'qualification': {'verdict': 'ready'}})['qualified']
    assert not verify_corpus_binding(db, manifest=manifest, protocol=PROTOCOL, receipt={'verdict': 'ready'})['qualified']


@pytest.mark.parametrize('mutation', ['tenant', 'source', 'method', 'cutoffs', 'omitted_series'])
def test_manifest_identity_mismatch_fails(db, bound, mutation):
    manifest, _, receipt = bound
    if mutation == 'tenant':
        changed = replace(manifest, org_id='other-org')
    elif mutation == 'method':
        changed = replace(manifest, method_version='other-v1')
    elif mutation == 'cutoffs':
        changed = replace(manifest, cutoffs=(AS_OF,))
    elif mutation == 'omitted_series':
        changed = replace(manifest, series=replace(manifest.series, series_keys=manifest.series.series_keys[:-1]))
    else:
        changed = replace(manifest, series=replace(manifest.series, params={'baseline': {
            **manifest.series.params['baseline'], 'sources': [{'source_id': 'other', 'methodology_version': 'permit-v1'}]}}))
    assert not verify_corpus_binding(db, manifest=changed, protocol=PROTOCOL, receipt=receipt)['qualified']


def test_unaudited_real_shape_stays_hold(db, bound):
    manifest, request, _ = bound
    request = request.model_copy(update={'coverage_audit': None})
    receipt = produce_corpus_binding(db, manifest=manifest, request=request, protocol=PROTOCOL)
    check = verify_corpus_binding(db, manifest=manifest, protocol=PROTOCOL, receipt=receipt)
    assert not check['qualified']
    assert check['verified']


def test_raw_record_kind_must_match_the_actual_permit_reader(db, bound):
    from app.models.ingestion import RawSourceRecord
    manifest, request, _ = bound
    db.execute(update(RawSourceRecord).values(record_type='filing'),
               execution_options={'synchronize_session': False})
    db.expire_all()
    changed = freeze(db, method_id=manifest.method_id, method_version=manifest.method_version,
                     series=manifest.series, cutoffs=manifest.cutoffs, thresholds={},
                     data_scope=manifest.data_scope)
    with pytest.raises(ValueError, match='raw|permit'):
        produce_corpus_binding(db, manifest=changed,
                               request=request.model_copy(update={'coverage_audit': None}),
                               protocol=PROTOCOL)


def test_weak_floors_and_future_replay_cutoff_rejected(db, bound):
    manifest, request, _ = bound
    for weakened in (request.model_copy(update={'min_fired_signals': 1}),
                     request.model_copy(update={'as_of': manifest.cutoffs[0] - timedelta(days=1)})):
        with pytest.raises(ValueError):
            produce_corpus_binding(db, manifest=manifest, request=weakened, protocol=PROTOCOL)


def test_replay_arguments_cannot_differ_from_frozen_manifest(db, bound):
    manifest, _, _ = bound
    with pytest.raises(ValueError, match='cutoffs'):
        replay(db, method_id=manifest.method_id, method_version=manifest.method_version,
               manifest=manifest, series=manifest.series, cutoffs=[AS_OF])
    with pytest.raises(ValueError, match='series'):
        replay(db, method_id=manifest.method_id, method_version=manifest.method_version,
               manifest=manifest, series=replace(manifest.series, methodology_version='other'),
               cutoffs=manifest.cutoffs)


def test_new_source_series_outside_manifest_invalidates_binding(db, bound):
    manifest, _, receipt = bound
    event = START + timedelta(days=12)
    load_rows(db, [dict(key='extra-bind', entity_id='extra', source_key='bind-source',
                       external_record_id='extra', attribute='permit.filed_at',
                       value=event.isoformat(), effective_at=event.isoformat(),
                       first_observed_at=event.isoformat(), recorded_at=event.isoformat(),
                       methodology_version='permit-v1', record_type='permit', source_type='permit',
                       geography={'city': 'Columbus', 'state': 'OH'})])
    assert not verify_corpus_binding(db, manifest=manifest, protocol=PROTOCOL, receipt=receipt)['qualified']


def test_code_drift_invalidates_binding(db, bound, monkeypatch):
    manifest, _, receipt = bound
    monkeypatch.setattr('eval.replay.manifest._module_hashes', lambda: {})
    assert not verify_corpus_binding(db, manifest=manifest, protocol=PROTOCOL, receipt=receipt)['qualified']


def test_structured_outcome_definition_is_undecidable_until_extracted(db, bound):
    manifest, _, _ = bound
    signal = CutoffSignal(manifest.cutoffs[0], 'fired', 70, [], 'synthetic', 'known_then')
    protocol = {**PROTOCOL, 'outcome_definition': {'value': {'name': 'sustained_elevated_activity'}}}
    result = verdict([signal], outcomes={signal.as_of: True}, protocol=protocol)
    assert result['verdict'] == 'corpus_not_qualified'


def test_forged_replay_signals_cannot_clear_bound_corpus_gate(db, bound):
    from app.services.temporal_service import fingerprint
    from eval.replay import dv_signal  # noqa: F401 — register the real method
    manifest, _, receipt = bound
    real = replay(db, method_id=manifest.method_id, method_version=manifest.method_version,
                  manifest=manifest, series=manifest.series, cutoffs=manifest.cutoffs)
    fake = replace(real.signals[0], status='fired', value=99, mode='known_then')
    altered = replace(real, signals=(fake,))
    # Even a recomputed self-consistent digest of fabricated results must fail.
    forged = replace(altered, run_fingerprint=fingerprint(altered.canonical()))
    result = verdict(forged, outcomes={fake.as_of: 110}, protocol=PROTOCOL,
                     db=db, corpus_binding=receipt)
    assert result['verdict'] == 'corpus_not_qualified'
    assert 'replay' in result['reason'].lower()


def test_legacy_request_only_audit_cannot_bind_data(db, bound):
    manifest, request, _ = bound
    audit = request.coverage_audit.model_copy(update={'attested_snapshot_id': None})
    with pytest.raises(ValueError, match='snapshot'):
        produce_corpus_binding(db, manifest=manifest,
                               request=request.model_copy(update={'coverage_audit': audit}),
                               protocol=PROTOCOL)


def test_old_audit_cannot_be_reused_for_newly_frozen_changed_data(db, bound):
    manifest, request, _ = bound
    db.execute(update(TemporalObservation).where(TemporalObservation.id == 'obs-bind-0')
               .values(confidence=0.25), execution_options={'synchronize_session': False})
    db.expire_all()
    new_manifest = freeze(db, method_id=manifest.method_id, method_version=manifest.method_version,
                          series=manifest.series, cutoffs=manifest.cutoffs, thresholds={},
                          data_scope='local_fixture')
    assert new_manifest.snapshot_id != manifest.snapshot_id
    with pytest.raises(ValueError, match='snapshot'):
        produce_corpus_binding(db, manifest=new_manifest, request=request, protocol=PROTOCOL)
