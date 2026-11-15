"""Regression tests for ArcGIS re-import snapshot collapse (Arlington issued).

Some ArcGIS layers (Arlington "Issued Permits") emit several rows for one real
permit, each a fresh ImportDate/OBJECTID snapshot sharing the derived business
identity (FOLDERYEAR-FOLDERSEQUENCE-FOLDERTYPE). They collapse to one
source_record_id downstream, so the health canary's duplicate-identity check
rejected the source. The connector now collapses to the latest snapshot per
identity while leaving pagination (keyset/offset) driven by the raw page.
"""
from __future__ import annotations

from app.services.ingestion.connectors.arcgis import (
    ArcGISConnector,
    _collapse_latest_by_identity,
)


def test_collapse_keeps_latest_snapshot_per_identity():
    rows = (
        {"FY": "2025", "SEQ": "100", "TY": "CP", "ImportDate": 10, "OBJECTID": 1},
        {"FY": "2025", "SEQ": "100", "TY": "CP", "ImportDate": 30, "OBJECTID": 7},  # newer
        {"FY": "2025", "SEQ": "100", "TY": "CP", "ImportDate": 20, "OBJECTID": 4},
        {"FY": "2025", "SEQ": "200", "TY": "CO", "ImportDate": 5, "OBJECTID": 2},
    )
    out = _collapse_latest_by_identity(rows, ("FY", "SEQ", "TY"), "ImportDate")
    assert len(out) == 2
    permit = next(r for r in out if r["SEQ"] == "100")
    assert permit["ImportDate"] == 30 and permit["OBJECTID"] == 7


def test_collapse_passes_through_rows_missing_identity_fields():
    rows = (
        {"FY": "2025", "SEQ": "100", "TY": "CP", "ImportDate": 1},
        {"FY": None, "SEQ": "100", "TY": "CP", "ImportDate": 9},  # unkeyable
    )
    out = _collapse_latest_by_identity(rows, ("FY", "SEQ", "TY"), "ImportDate")
    # The unkeyable row is never silently dropped.
    assert len(out) == 2


def test_collapse_missing_recency_sorts_oldest():
    rows = (
        {"FY": "1", "SEQ": "1", "TY": "CP", "ImportDate": None},
        {"FY": "1", "SEQ": "1", "TY": "CP", "ImportDate": 5},
    )
    out = _collapse_latest_by_identity(rows, ("FY", "SEQ", "TY"), "ImportDate")
    assert len(out) == 1 and out[0]["ImportDate"] == 5


class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self, endpoint, params=None, headers=None):  # noqa: D401
        return self._payload


def _feature(fy, seq, ty, import_date, oid):
    return {
        "attributes": {
            "FOLDERYEAR": fy, "FOLDERSEQUENCE": seq, "FOLDERTYPE": ty,
            "ImportDate": import_date, "OBJECTID": oid,
        }
    }


def test_connector_collapses_but_cursor_uses_raw_page():
    # ArcGIS returns the page ordered by OBJECTID ASC (keyset order), so the
    # last raw row carries the max cursor value. Two rows are snapshots of the
    # same permit (seq 100): an older import (oid 1) and a newer one (oid 9).
    payload = {
        "features": [
            _feature("2025", "100", "CP", 10, 1),   # older snapshot of permit 100
            _feature("2025", "200", "CO", 20, 5),
            _feature("2025", "100", "CP", 30, 9),   # newer snapshot of permit 100 (max OBJECTID)
        ],
        "exceededTransferLimit": True,
    }
    connector = ArcGISConnector(
        "https://example.test/MapServer/1/query",
        out_fields="*",
        keyset_field="OBJECTID",
        collapse_identity_fields=("FOLDERYEAR", "FOLDERSEQUENCE", "FOLDERTYPE"),
        collapse_recency_field="ImportDate",
        http_client=_StubClient(payload),
    )
    envelope = connector.fetch()
    ids = sorted((r["FOLDERSEQUENCE"], r["ImportDate"]) for r in envelope.records)
    # One row per permit identity, keeping the latest ImportDate snapshot.
    assert ids == [("100", 30), ("200", 20)]
    # Cursor advances off the RAW page's max OBJECTID (9), not the collapsed set,
    # so collapsing a snapshot can never skip the next page.
    assert envelope.next_checkpoint == {"keyset": {"OBJECTID": 9}}


def test_connector_requires_recency_when_identity_configured():
    import pytest

    with pytest.raises(ValueError):
        ArcGISConnector(
            "https://example.test/MapServer/1/query",
            collapse_identity_fields=("FOLDERYEAR",),
        )
