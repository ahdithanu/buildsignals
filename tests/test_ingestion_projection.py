from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.schemas.ingestion import FieldMappingCreate
from app.services.ingestion import health
from app.services.ingestion.connectors import ConnectorResponseError, FetchEnvelope
from app.services.ingestion.service import validate_source_projection


@pytest.mark.parametrize("fields", [None, [], "PROP_LOC", [None], [""]])
def test_strict_projection_rejects_invalid_allowlist(fields):
    with pytest.raises(ValueError, match="nonempty field allowlist"):
        validate_source_projection((), {"enforce_field_allowlist": True, "field_allowlist": fields})


def test_strict_projection_rejects_a_whole_page_without_echoing_payload():
    with pytest.raises(ConnectorResponseError) as error:
        validate_source_projection(
            ({"PROP_LOC": "site"}, {"PROP_LOC": "site", "ST_ADDRESS": "DO_NOT_RETAIN"}),
            {"enforce_field_allowlist": True, "field_allowlist": ["PROP_LOC"]},
        )
    assert str(error.value) == "Source response exceeds reviewed field scope"


def test_projection_is_opt_in_and_accepts_exact_allowed_rows():
    validate_source_projection(({"anything": "unchanged legacy contract"},), {})
    validate_source_projection(({"PROP_LOC": "site"},),
                               {"enforce_field_allowlist": True, "field_allowlist": ["PROP_LOC"]})


def _canary_source():
    return SimpleNamespace(
        id="projection-test", key="projection-test", adapter="csv",
        record_type="permit", base_url="https://example.test/public.csv",
        settings={
            "enforce_field_allowlist": True,
            "field_allowlist": ["id", "loaded_at"],
            "connector": {},
            "defaults": {"approval_stage": "approved"},
        },
        field_mappings=[FieldMappingCreate(
            source_field="id", canonical_field="source_record_id", is_required=True,
        )],
    )


@pytest.mark.parametrize("phase", ["main", "stage", "freshness"])
def test_strict_projection_rejects_poisoned_rows_in_every_canary_phase(monkeypatch, phase):
    source = _canary_source()
    if phase == "stage":
        source.settings["canary_stage_probes"] = [{"expected_stage": "approved"}]
    elif phase == "freshness":
        source.settings.update(
            freshness_field="loaded_at", freshness_semantics="record_updated_at",
            canary_freshness_probe={"sample_size": 2},
        )
    clean = {"id": "safe", "loaded_at": "2026-11-11T00:00:00Z"}
    poisoned = {**clean, "id": "poisoned", "ST_ADDRESS": "DO_NOT_RETAIN"}
    pages = [FetchEnvelope(
        source="test", records=(clean, poisoned), checkpoint=None, has_more=False,
    )]
    if phase != "main":
        pages.insert(0, FetchEnvelope(
            source="test", records=(clean,), checkpoint=None, has_more=False,
        ))
    fetched = []

    def build_connector(*args, **kwargs):
        def fetch():
            fetched.append(1)
            return pages.pop(0)
        return SimpleNamespace(fetch_page=fetch)

    monkeypatch.setattr(health, "build_connector", build_connector)
    with pytest.raises(ConnectorResponseError, match="reviewed field scope") as error:
        health.validate_source_canary(
            source, sample_size=2, now=datetime(2026, 11, 11, 12, tzinfo=timezone.utc),
        )
    assert "DO_NOT_RETAIN" not in str(error.value)
    assert len(fetched) == (1 if phase == "main" else 2)


def test_strict_canary_configuration_fails_before_constructing_transport(monkeypatch):
    source = _canary_source()
    source.settings["field_allowlist"] = None

    def forbidden(*args, **kwargs):
        pytest.fail("invalid allowlist reached transport construction")

    monkeypatch.setattr(health, "build_connector", forbidden)
    with pytest.raises(ValueError, match="nonempty field allowlist"):
        health.validate_source_canary(source)
