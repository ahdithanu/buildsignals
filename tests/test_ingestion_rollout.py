from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from app.schemas.ingestion import IngestionSourceCreate
from app.services.ingestion.catalog import load_candidate_catalog, load_catalog
from app.services.ingestion.host_policy import audit_ingestion_hosts
from app.services.ingestion.rollout import (
    DEFAULT_ROLLOUT_MANIFEST_PATH,
    build_production_rollout_manifest,
    rollout_manifest_json,
    source_rollout_wave,
)


def _manifest():
    return build_production_rollout_manifest(
        load_catalog(),
        candidates=load_candidate_catalog(),
        shard_count=4,
    )


def test_rollout_manifest_is_deterministic_and_checked_in():
    manifest = _manifest()

    assert rollout_manifest_json(manifest) == rollout_manifest_json(_manifest())
    assert DEFAULT_ROLLOUT_MANIFEST_PATH.read_text(encoding="utf-8") == (
        rollout_manifest_json(manifest)
    )
    assert json.loads(DEFAULT_ROLLOUT_MANIFEST_PATH.read_text(encoding="utf-8")) == (
        asdict(manifest)
    )


def test_rollout_manifest_assigns_every_source_to_one_wave_and_shard():
    entries = load_catalog()
    manifest = _manifest()
    all_wave_keys = [key for wave in manifest.waves for key in wave.source_keys]

    assert manifest.source_count == len(entries) == 131
    assert manifest.state_count == 41
    assert len(all_wave_keys) == len(set(all_wave_keys)) == len(entries)
    assert set(all_wave_keys) == {entry.key for entry in entries}

    for wave in manifest.waves:
        shard_keys = [key for shard in wave.shards for key in shard.source_keys]
        assert len(shard_keys) == len(set(shard_keys)) == wave.source_count
        assert set(shard_keys) == set(wave.source_keys)
        assert sum(shard.source_count for shard in wave.shards) == wave.source_count


def test_rollout_manifest_matches_catalog_wave_classification():
    entries = load_catalog()
    manifest = _manifest()
    wave_by_key = {
        key: wave.wave for wave in manifest.waves for key in wave.source_keys
    }

    assert wave_by_key == {entry.key: source_rollout_wave(entry) for entry in entries}
    assert [(wave.wave, wave.source_count) for wave in manifest.waves] == [
        (1, 27),
        (2, 26),
        (3, 11),
        (4, 67),
    ]


def test_rollout_manifest_candidate_scope_excludes_promoted_sources():
    manifest = _manifest()

    assert manifest.candidate_retries.candidate_count == 0
    assert manifest.candidate_retries.candidate_keys == []
    assert manifest.candidate_retries.required_hosts == []
    assert manifest.candidate_retries.allowed_hosts_value == ""


def test_render_savannah_worker_is_pinned_to_reviewed_scope():
    source = next(
        entry for entry in load_catalog()
        if entry.key == "savannah_ga_commercial_building_permits"
    )
    manifest = _manifest()
    host_policy = audit_ingestion_hosts([source], allowed_hosts="pub.sagis.org")
    blueprint = Path("render.yaml").read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^  - type: cron\n"
        r"    name: dealsignal-savannah-permit-ingestion\n"
        r"(?P<body>.*?)(?=^  - type:|\Z)",
        blueprint,
    )

    assert match is not None
    worker = match.group("body")
    assert 'schedule: "30 10 * * 1"' in worker
    assert "--source-key savannah_ga_commercial_building_permits" in worker
    assert "--rollout-wave 4" in worker
    assert "value: pub.sagis.org" in worker
    assert f"value: {host_policy.policy_digest}" in worker
    assert f"value: {manifest.manifest_digest}" in worker


def test_render_dallas_worker_is_pinned_to_reviewed_production_scope():
    source = next(
        entry for entry in load_catalog()
        if entry.key == "dallas_tx_legistar_planning_agendas"
    )
    manifest = _manifest()
    host_policy = audit_ingestion_hosts(
        [source], allowed_hosts="webapi.legistar.com"
    )
    blueprint = Path("render.yaml").read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^  - type: cron\n"
        r"    name: dealsignal-dallas-planning-ingestion\n"
        r"(?P<body>.*?)(?=^  - type:|\Z)",
        blueprint,
    )

    assert match is not None
    worker = match.group("body")
    assert "scheduled-due" in worker
    assert "--source-key dallas_tx_legistar_planning_agendas" in worker
    assert "--rollout-wave 1" in worker
    assert "--max-pages-per-source 10" in worker
    assert "value: webapi.legistar.com" in worker
    assert f"value: {host_policy.policy_digest}" in worker
    assert f"value: {manifest.manifest_digest}" in worker


def test_render_wave_one_worker_rotates_reviewed_shards_in_plan_only_mode():
    entries = load_catalog()
    manifest = _manifest()
    wave = manifest.waves[0]
    host_policy = audit_ingestion_hosts(
        [entry for entry in entries if source_rollout_wave(entry) == 1],
        allowed_hosts=wave.required_hosts,
    )
    blueprint = Path("render.yaml").read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^  - type: cron\n"
        r"    name: dealsignal-permit-ingestion-cohort-1\n"
        r"(?P<body>.*?)(?=^  - type:|\Z)",
        blueprint,
    )

    assert match is not None
    worker = match.group("body")
    assert 'schedule: "15 */6 * * *"' in worker
    assert "startCommand: ./scripts/daily-ingestion.sh" in worker
    assert f"value: {','.join(wave.required_hosts)}" in worker
    assert f"value: {host_policy.policy_digest}" in worker
    assert f"value: {manifest.manifest_digest}" in worker
    assert 'key: INGESTION_ROLLOUT_WAVE\n        value: "1"' in worker
    assert 'key: INGESTION_SHARD_COUNT\n        value: "4"' in worker
    assert 'key: INGESTION_ROTATE_SHARDS\n        value: "true"' in worker
    assert 'key: INGESTION_PLAN_ONLY\n        value: "true"' in worker


def test_daily_ingestion_runner_preflights_reviewed_rollout_scope():
    runner = Path("scripts/daily-ingestion.sh").read_text(encoding="utf-8")

    assert "catalog rollout-manifest --check" in runner
    assert "catalog host-audit" in runner
    assert 'HOST_AUDIT_ARGS+=(--rollout-wave "$ROLLOUT_WAVE")' in runner
    assert 'ARGS+=(--rollout-wave "$ROLLOUT_WAVE")' in runner
    assert "UTC_HOUR * SHARD_COUNT / 24" in runner


def test_daily_ingestion_runner_rotates_to_the_current_utc_shard(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "python-commands.log"
    fake_date = fake_bin / "date"
    fake_python = fake_bin / "python"
    fake_date.write_text("#!/bin/sh\nprintf '18\\n'\n", encoding="utf-8")
    fake_python.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {command_log}\n",
        encoding="utf-8",
    )
    fake_date.chmod(0o755)
    fake_python.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "ENVIRONMENT": "development",
        "INGESTION_ORGANIZATION": "default-org",
        "INGESTION_PLAN_ONLY": "true",
        "INGESTION_ROLLOUT_WAVE": "1",
        "INGESTION_SHARD_COUNT": "4",
        "INGESTION_ROTATE_SHARDS": "true",
    }

    result = subprocess.run(
        ["bash", "scripts/daily-ingestion.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "shard=3/4" in result.stdout
    command = command_log.read_text(encoding="utf-8")
    assert "scheduled-due" in command
    assert "--rollout-wave 1" in command
    assert "--shard-count 4" in command
    assert "--shard-index 3" in command
    assert "--plan-only" in command


def test_rollout_classification_uses_settings_state_and_rejects_unknown_state():
    settings_state = IngestionSourceCreate(
        key="settings_state",
        name="Settings State",
        adapter="csv",
        jurisdiction="Regional feed",
        base_url="https://example.gov/data.csv",
        settings={"state": "TX", "connector": {}},
    )
    unknown = settings_state.model_copy(update={
        "key": "unknown",
        "settings": {"connector": {}},
    })

    assert source_rollout_wave(settings_state) == 1
    with pytest.raises(ValueError, match="no valid US state or district"):
        source_rollout_wave(unknown)


@pytest.mark.parametrize("field", ["adapter", "is_active", "field_mappings"])
def test_catalog_fingerprint_covers_behavior_critical_source_fields(field):
    source = IngestionSourceCreate(
        key="source",
        name="Source",
        adapter="csv",
        jurisdiction="Austin, TX",
        base_url="https://example.gov/data.csv",
        settings={"connector": {}},
    )
    updates = {
        "adapter": "arcgis",
        "is_active": False,
        "field_mappings": [{
            "source_field": "permit_id",
            "canonical_field": "source_record_id",
        }],
    }
    payload = source.model_dump(mode="json")
    payload[field] = updates[field]
    changed = IngestionSourceCreate.model_validate(payload)

    original = build_production_rollout_manifest([source])
    modified = build_production_rollout_manifest([changed])

    assert modified.catalog_fingerprint != original.catalog_fingerprint
    assert modified.manifest_digest != original.manifest_digest
