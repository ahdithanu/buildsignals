import pytest

from app.services.ingestion.connectors.base import InvalidCheckpointError
from app.services.ingestion.connectors.csv import CSVConnector
from app.services.ingestion.connectors.factory import build_connector


def test_snapshot_resume_preserves_ids_and_evidence(tmp_path):
    source = tmp_path / "parcels.csv"
    source.write_text("STRAP,acres\n000001,2\n000002,3\n")
    connector = CSVConnector(source, page_size=1, verify_snapshot=True)
    first = connector.fetch()
    second = connector.fetch(first.checkpoint)
    assert first.records[0]["STRAP"] == "000001"
    assert second.records[0]["STRAP"] == "000002"
    assert first.metadata["snapshot_sha256"] == second.metadata["snapshot_sha256"]
    assert second.has_more is False


def test_changed_snapshot_requires_explicit_restart(tmp_path):
    source = tmp_path / "parcels.csv"
    source.write_text("id\n1\n2\n")
    connector = CSVConnector(source, page_size=1, verify_snapshot=True)
    checkpoint = connector.fetch().checkpoint
    source.write_text("id\n0\n1\n2\n")
    with pytest.raises(InvalidCheckpointError, match="restart"):
        connector.fetch(checkpoint)
    assert connector.fetch().records[0]["id"] == "0"


def test_unfingerprinted_checkpoint_is_rejected_in_verified_mode(tmp_path):
    source = tmp_path / "parcels.csv"
    source.write_text("id\n1\n2\n")
    with pytest.raises(InvalidCheckpointError):
        CSVConnector(source, verify_snapshot=True).fetch({"row_offset": 1})


def test_factory_rejects_string_boolean():
    with pytest.raises(ValueError, match="boolean"):
        build_connector("csv", {"source": "https://example.com/data.csv", "verify_snapshot": "false"})
