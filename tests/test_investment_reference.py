"""Frozen annual public references are validated without fetching or tenant data."""
from __future__ import annotations

import hashlib
import json
import socket
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.services import investment_inputs as inputs
from app.services import investment_reference as reference
from app.services.investment_model import rank_metros
from scripts import build_investment_reference as builder


def identity(snapshot):
    value = {"version": "official-current-vintage-2025-v2", "year": 2025,
             "sources": [{"url": p["url"], "sha256": p["sha256"]}
                         for p in snapshot["provenance"]], "metros": snapshot["metros"]}
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode()).hexdigest()


def snapshot():
    captured = "2026-11-10T07:00:00+00:00"
    context = {"name": "Synthetic", "population_2024": 1000,
               "population_2025": 1010, "net_migration_2025": -2}
    result = {"year": 2025, "captured_at": captured,
              "provenance": [{"url": url, "period": period, "captured_at": captured,
                              "sha256": str(index) * 64}
                             for index, (url, period) in enumerate(reference.SOURCES, 1)],
              "metros": [{"cbsa": str(10000 + i), **context,
                          "hpi": {2023: 100, 2025: 110 + i},
                          "units": {2022: 100, 2023: 100, 2024: 100, 2025: 110 + i},
                          "counties": [str(20000 + i)]} for i in range(20)],
              "context_metros": {str(10000 + i): dict(context) for i in range(20)}}
    result["context_metros"]["45300"] = {**context, "name": "Synthetic Tampa"}
    result["snapshot_id"] = identity(result)
    return result


@pytest.fixture
def package(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "REFERENCE_PATH", tmp_path / "investment-reference-2025.json")
    monkeypatch.setattr(reference, "MANIFEST_PATH", tmp_path / "investment-reference-2025.manifest.json")
    return tmp_path


def write_package(data=None):
    payload = {"schema_version": reference.SCHEMA_VERSION,
               "code_version": reference.code_version(), "year": 2025,
               "min_cohort": reference.MIN_COHORT, "snapshot": data or snapshot()}
    write_payload(payload)
    return payload


def write_payload(payload):
    body = json.dumps(payload, allow_nan=True).encode()
    reference.REFERENCE_PATH.write_bytes(body)
    reference.MANIFEST_PATH.write_text(json.dumps({
        "schema_version": reference.SCHEMA_VERSION,
        "artifact_filename": reference.REFERENCE_PATH.name,
        "artifact_sha256": hashlib.sha256(body).hexdigest()}))


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Reference loader attempted network access")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(inputs.RetryingHttpClient, "get_bytes", blocked)


def test_json_roundtrip_preserves_full_rank_context_dates_and_provenance(package):
    original = snapshot()
    write_package(original)
    loaded = reference.load_reference_snapshot()
    assert loaded == {**original, "input_mode": "release_reference",
                      "artifact_sha256": hashlib.sha256(reference.REFERENCE_PATH.read_bytes()).hexdigest()}
    assert rank_metros(loaded) == rank_metros(original)
    assert loaded["context_metros"]["45300"]["net_migration_2025"] == -2
    loaded["context_metros"]["45300"]["name"] = "changed caller copy"
    assert reference.load_reference_snapshot()["context_metros"] == original["context_metros"]


@pytest.mark.parametrize("file", ["REFERENCE_PATH", "MANIFEST_PATH"])
def test_missing_file_fails_closed(package, file):
    write_package()
    getattr(reference, file).unlink()
    with pytest.raises(reference.ReferenceUnavailable):
        reference.load_reference_snapshot()


@pytest.mark.parametrize("file", ["REFERENCE_PATH", "MANIFEST_PATH"])
@pytest.mark.parametrize("body", [b"{broken", b"\xff", b"[]", b"{}"])
def test_corrupt_files_fail_closed(package, file, body):
    write_package()
    getattr(reference, file).write_bytes(body)
    with pytest.raises(reference.ReferenceUnavailable):
        reference.load_reference_snapshot()


@pytest.mark.parametrize("change", ["context", "timestamp"])
def test_manifest_binds_context_and_timestamps_even_when_snapshot_id_does_not(package, change):
    payload = write_package()
    original_id = payload["snapshot"]["snapshot_id"]
    if change == "context":
        payload["snapshot"]["context_metros"]["45300"]["name"] = "tampered"
    else:
        payload["snapshot"]["captured_at"] = "2026-11-11T07:00:00+00:00"
    assert identity(payload["snapshot"]) == original_id
    reference.REFERENCE_PATH.write_text(json.dumps(payload))
    with pytest.raises(reference.ReferenceUnavailable, match="hash"):
        reference.load_reference_snapshot()


@pytest.mark.parametrize("field,value", [
    ("schema_version", "unknown"), ("year", 2024), ("year", True),
    ("min_cohort", 1), ("min_cohort", 20.0), ("code_version", {}),
])
def test_incompatible_envelope_rejected_with_matching_hash(package, field, value):
    payload = write_package()
    payload[field] = value
    write_payload(payload)
    with pytest.raises(reference.ReferenceUnavailable):
        reference.load_reference_snapshot()


@pytest.mark.parametrize("change", [
    "year", "short_cohort", "snapshot_id", "extra_tenant_field", "missing_context",
    "naive_time", "provenance_url", "provenance_period", "provenance_hash",
    "provenance_time", "provenance_missing", "context_mismatch", "duplicate_county",
    "invalid_cbsa", "year_key", "missing_year", "nonfinite", "negative_units",
    "boolean_hpi", "invalid_population", "invalid_migration",
])
def test_invalid_snapshot_rejected_even_with_matching_artifact_hash(package, change):
    payload = write_package()
    data = payload["snapshot"]
    metro = data["metros"][0]
    if change == "year":
        data["year"] = 2024
    elif change == "short_cohort":
        data["metros"].pop()
    elif change == "snapshot_id":
        data["snapshot_id"] = "0" * 64
    elif change == "extra_tenant_field":
        data["local_evidence"] = {}
    elif change == "missing_context":
        del data["context_metros"]
    elif change == "naive_time":
        data["captured_at"] = "2026-11-10T07:00:00"
    elif change.startswith("provenance_"):
        field = change.removeprefix("provenance_")
        if field == "missing":
            data["provenance"].pop()
        else:
            field = {"hash": "sha256", "time": "captured_at"}.get(field, field)
            data["provenance"][0][field] = "invalid"
    elif change == "context_mismatch":
        data["context_metros"][metro["cbsa"]]["population_2025"] += 1
    elif change == "duplicate_county":
        data["metros"][1]["counties"] = metro["counties"]
    elif change == "invalid_cbsa":
        metro["cbsa"] = "abcde"
    elif change == "year_key":
        metro["hpi"]["02025"] = metro["hpi"].pop(2025)
    elif change == "missing_year":
        del metro["units"][2022]
    elif change == "nonfinite":
        metro["hpi"][2025] = float("nan")
    elif change == "negative_units":
        metro["units"][2025] = -1
    elif change == "boolean_hpi":
        metro["hpi"][2025] = True
    elif change == "invalid_population":
        metro["population_2024"] = "1000"
    elif change == "invalid_migration":
        data["context_metros"]["45300"]["net_migration_2025"] = float("inf")
    write_payload(payload)
    with pytest.raises(reference.ReferenceUnavailable):
        reference.load_reference_snapshot()


def test_byte_limits_and_duplicate_json_keys(package):
    write_package()
    reference.REFERENCE_PATH.write_bytes(b" " * (reference.MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(reference.ReferenceUnavailable, match="size"):
        reference.load_reference_snapshot()
    write_package()
    reference.MANIFEST_PATH.write_text('{"schema_version":"a","schema_version":"b"}')
    with pytest.raises(reference.ReferenceUnavailable):
        reference.load_reference_snapshot()


@pytest.mark.parametrize("field,value", [
    ("schema_version", "unknown"), ("artifact_filename", "../other.json"),
    ("artifact_sha256", "0" * 64),
])
def test_invalid_manifest_pins_fail_closed(package, field, value):
    write_package()
    manifest = json.loads(reference.MANIFEST_PATH.read_bytes())
    manifest[field] = value
    reference.MANIFEST_PATH.write_text(json.dumps(manifest))
    with pytest.raises(reference.ReferenceUnavailable):
        reference.load_reference_snapshot()


def test_parser_fingerprint_mismatch_rejected(package):
    payload = write_package()
    payload["code_version"]["inputs_sha256"] = "0" * 64
    write_payload(payload)
    with pytest.raises(reference.ReferenceUnavailable, match="code version"):
        reference.load_reference_snapshot()


@pytest.mark.parametrize("change", ["duplicate_cbsa", "zero_baseline"])
def test_ranker_guards_still_apply_with_recomputed_snapshot_identity(package, change):
    data = snapshot()
    if change == "duplicate_cbsa":
        data["metros"].append({**deepcopy(data["metros"][0]), "counties": ["99999"]})
    else:
        data["metros"][0]["units"] = {2022: 0, 2023: 0, 2024: 0, 2025: 1}
    data["snapshot_id"] = identity(data)
    write_package(data)
    with pytest.raises(reference.ReferenceUnavailable):
        reference.load_reference_snapshot()


def test_unknown_demand_context_is_preserved_without_fabrication(package):
    data = snapshot()
    for field in ("population_2024", "population_2025", "net_migration_2025"):
        data["context_metros"]["45300"][field] = None
    write_package(data)
    assert reference.load_reference_snapshot()["context_metros"]["45300"] == data["context_metros"]["45300"]


def test_impossible_context_integer_rejected(package):
    data = snapshot()
    data["context_metros"]["45300"]["population_2025"] = 10**400
    write_package(data)
    with pytest.raises(reference.ReferenceUnavailable):
        reference.load_reference_snapshot()


def test_packaged_annual_release_has_full_offline_cohort_and_context():
    loaded = reference.load_reference_snapshot()
    assert loaded["input_mode"] == "release_reference"
    assert loaded["year"] == 2025
    assert loaded["snapshot_id"] == "523fea1590d2bd056ec511f0e679e5c1e738a7303f26335aeadbfc88fc0bdd98"
    assert loaded["artifact_sha256"] == hashlib.sha256(reference.REFERENCE_PATH.read_bytes()).hexdigest()
    ranked = rank_metros(loaded)
    assert len(ranked) == len(loaded["metros"]) == 360
    assert "45300" not in {metro["cbsa"] for metro in ranked}
    assert "Tampa" in loaded["context_metros"]["45300"]["name"]
    assert len(loaded["provenance"]) == 6
    assert all(source["captured_at"] == loaded["captured_at"] for source in loaded["provenance"])


def test_builder_roundtrip_and_no_overwrite_before_fetch(package, monkeypatch):
    original = snapshot()
    calls = []
    monkeypatch.setattr(inputs, "get_snapshot", lambda: calls.append(1) or deepcopy(original))
    result = builder.build_reference()
    assert result["cohort_size"] == 20
    assert result["snapshot_id"] == original["snapshot_id"]
    assert result["captured_at"] == original["captured_at"]
    assert reference.load_reference_snapshot()["provenance"] == original["provenance"]
    with pytest.raises(FileExistsError):
        builder.build_reference()
    assert calls == [1]


def test_generator_cli_requires_explicit_capture_opt_in(monkeypatch):
    monkeypatch.setattr("sys.argv", ["build_investment_reference.py"])
    with pytest.raises(SystemExit) as exc:
        builder.main()
    assert exc.value.code == 2


def test_builder_performs_exactly_six_official_gets(package):
    from tests.test_investment_inputs import Client

    client = Client()
    # Repeat synthetic counties/metros so the real parsers produce an eligible cohort.
    import csv
    import io

    for url, body in list(client.bodies.items()):
        encoding = "utf-8" if url == inputs.HPI_URL else "cp1252"
        rows = list(csv.reader(io.StringIO(body.decode(encoding))))
        header_count = 0 if url == inputs.HPI_URL else 1 if url == inputs.POP_URL else 2
        expanded = rows[:header_count]
        for i in range(20):
            for row in rows[header_count:]:
                if not row:
                    continue
                row = list(row)
                if url == inputs.HPI_URL:
                    row[1] = str(10000 + i)
                elif url == inputs.POP_URL:
                    row[0] = str(10000 + i)
                    if row[2]:
                        row[2] = f"{i + 1:02d}" + row[2][-3:]
                else:
                    row[1] = f"{i + 1:02d}"
                expanded.append(row)
        stream = io.StringIO(newline="")
        csv.writer(stream).writerows(expanded)
        client.bodies[url] = stream.getvalue().encode(encoding)
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    result = builder.build_reference(http_client=client, now=now)
    assert client.calls == [url for url, _period in reference.SOURCES]
    assert result["cohort_size"] == 20
    assert reference.load_reference_snapshot()["captured_at"] == now.isoformat()
