import hashlib
import json

import pytest

from scripts.franklin_parcel_qualification import (
    combine_batches,
    county_reference,
    main,
    qualify_sample,
)


@pytest.mark.parametrize("reference", [None, 10066782, "010-066782", "01006678200", " 010066782", "01006678X"])
def test_rejects_unsupported_namespace(reference):
    assert county_reference(reference) is None


def test_preserves_leading_zero():
    assert county_reference("010066782") == "010-066782"


def test_sample_counts_and_no_acceptance():
    permits = [
        {"parcel_id": "010000001", "address": "55 E STATE ST"},
        {"parcel_id": "010000002", "address": "1066 NORTON RD"},
        {"parcel_id": "010000003", "address": "ONE ST"},
        {"parcel_id": "010000004", "address": "OTHER ST"},
        {"parcel_id": "010000005", "address": None},
        {"parcel_id": None},
    ]
    rows = [
        ("010-000001", "55 E STATE ST"),
        ("010-000002", "1058 - 1110 NORTON RD"),
        ("010-000003", "ONE ST"), ("010-000003", "ONE ST"),
        ("010-000005", "FIVE ST"),
    ]
    response = {"features": [{"attributes": {"PARCELID": key, "SITEADDRESS": address}}
                             for key, address in rows]}
    report = qualify_sample(permits, response)
    assert report["evaluated_permits"] == 6
    assert all(value == 1 for value in report["counts"].values())
    assert report["identity_verified"] is False
    assert report["production_eligible"] is False


@pytest.mark.parametrize("response", [
    {"error": {"code": 403}}, {"features": [], "exceededTransferLimit": True},
    {}, {"features": [{"attributes": {}}]},
])
def test_failure_is_not_zero_matches(response):
    with pytest.raises(ValueError):
        qualify_sample([], response)


@pytest.mark.parametrize("permits,response", [
    (None, {"features": []}), ([None], {"features": []}),
    ([], None), ([], {"features": [None]}),
    ([], {"features": [], "error": None}),
    ([], {"features": [{"attributes": {"PARCELID": " "}}]}),
    ([{"address": 123}], {"features": []}),
    ([], {"features": [{"attributes": {"PARCELID": "010-000001", "SITEADDRESS": 123}}]}),
])
def test_malformed_evidence_is_rejected(permits, response):
    with pytest.raises(ValueError):
        qualify_sample(permits, response)


def test_permit_count_is_not_unique_parcel_count():
    report = qualify_sample(
        [{"parcel_id": "010000001"}, {"parcel_id": "010000001"}],
        {"features": [{"attributes": {"PARCELID": "010-000001"}}]},
    )
    assert report["evaluated_permits"] == 2
    assert report["distinct_supported_references"] == 1
    assert report["returned_parcel_rows"] == report["distinct_returned_parcel_ids"] == 1


def test_cli_receipt_hashes_exact_inputs_and_omits_unselected_fields(tmp_path, capsys):
    permits = tmp_path / "permits.json"
    parcels = tmp_path / "parcels.json"
    permits.write_text('[{"parcel_id":"010000001","address":"ONE ST"}]')
    parcels.write_text(json.dumps({"features": [{"attributes": {
        "PARCELID": "010-000001", "SITEADDRESS": "ONE ST", "OWNERNME1": "DO NOT OUTPUT",
    }}]}))
    original = (permits.read_bytes(), parcels.read_bytes())
    main(["--permits", str(permits), "--parcels", str(parcels)])
    output = capsys.readouterr().out
    report = json.loads(output)
    assert "DO NOT OUTPUT" not in output
    assert "ONE ST" not in output
    assert report["input_sha256"] == {
        "permits": hashlib.sha256(original[0]).hexdigest(),
        "parcels": hashlib.sha256(original[1]).hexdigest(),
    }
    assert report["measured_at"].endswith("+00:00")
    assert report["counts"]["street_match_only"] == 1
    assert (permits.read_bytes(), parcels.read_bytes()) == original


def test_cli_failure_has_no_report_or_private_path(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--permits", str(tmp_path / "private-missing.json"), "--parcels", "absent"])
    output = capsys.readouterr()
    assert exc.value.code == 2
    assert output.out == ""
    assert "private-missing" not in output.err


def test_input_limits(tmp_path, monkeypatch):
    from scripts import franklin_parcel_qualification as module

    monkeypatch.setattr(module, "MAX_RECORDS", 1)
    with pytest.raises(ValueError):
        qualify_sample([{}, {}], {"features": []})
    with pytest.raises(ValueError):
        qualify_sample([], {"features": [{}, {}]})
    monkeypatch.setattr(module, "MAX_INPUT_BYTES", 2)
    evidence = tmp_path / "oversize.json"
    evidence.write_text("[{}]")
    with pytest.raises(ValueError):
        module._read_evidence(evidence)


def test_complete_batch_manifest_measures_repeated_permits_without_double_counting_parcels():
    permits = [
        {"parcel_id": "010000001", "address": "ONE ST"},
        {"parcel_id": "010000001", "address": "ONE ST"},
        {"parcel_id": "010000002", "address": "TWO ST"},
    ]
    batches = [
        {"requested_references": ["010-000001"], "response": {"features": [
            {"attributes": {"PARCELID": "010-000001", "SITEADDRESS": "ONE ST"}},
        ]}},
        {"requested_references": ["010-000002"], "response": {"features": []}},
    ]
    report = qualify_sample(permits, combine_batches(permits, batches))
    assert report["evaluated_permits"] == 3
    assert report["distinct_supported_references"] == 2
    assert report["counts"]["street_match_only"] == 2
    assert report["counts"]["unmatched"] == 1
    assert report["production_eligible"] is False


@pytest.mark.parametrize("batches", [
    [],
    [{"requested_references": ["010-000002"], "response": {"features": []}}],
    [{"requested_references": ["010-000001"], "response": {"features": [], "exceededTransferLimit": True}}],
    [{"requested_references": ["010-000001"], "response": {"error": {"code": 403}}}],
    [{"requested_references": ["010-000001", "010-000001"], "response": {"features": []}}],
    [{"requested_references": ["010-000001"], "response": {"features": []}},
     {"requested_references": ["010-000001"], "response": {"features": []}}],
    [{"requested_references": ["010-000001"], "response": {"features": [
        {"attributes": {"PARCELID": "010-000002"}},
    ]}}],
])
def test_batch_manifest_rejects_incomplete_or_untrusted_responses(batches):
    with pytest.raises(ValueError):
        combine_batches([{"parcel_id": "010000001"}], batches)


def test_batch_manifest_cli_receipt(tmp_path, capsys):
    permits = tmp_path / "permits.json"
    batches = tmp_path / "batches.json"
    permits.write_text('[{"parcel_id":"010000001","address":"ONE ST"}]')
    batches.write_text(json.dumps([{"requested_references": ["010-000001"],
        "response": {"features": [{"attributes": {"PARCELID": "010-000001",
        "SITEADDRESS": "ONE ST"}}]}}]))
    main(["--permits", str(permits), "--batch-manifest", str(batches)])
    report = json.loads(capsys.readouterr().out)
    assert report["response_mode"] == "complete_batch_manifest"
    assert report["input_sha256"]["batch_manifest"] == hashlib.sha256(batches.read_bytes()).hexdigest()
