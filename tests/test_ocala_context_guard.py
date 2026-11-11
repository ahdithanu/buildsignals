"""Synthetic, offline safety contract for the Ocala context connector wrapper."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.ingestion import service
from app.services.ingestion.connectors.base import FetchEnvelope
from scripts import recurring_regions as worker


def row(identity="SYNTHETIC-1", **updates):
    result = {"PermitNo": identity, "OBJECTID": 1, "Status": "IN REVIEW",
              "Subtype": "Commercial", "APN": "synthetic-parcel",
              "centroid": {"x": -82.14, "y": 29.18, "spatialReference": {"wkid": 4326}}}
    result.update(updates)
    return result


def envelope(records=(), *, offset=None, spatial_reference=None):
    return FetchEnvelope(source="synthetic", records=tuple(records),
                         has_more=offset is not None,
                         checkpoint={"offset": offset} if offset is not None else None,
                         metadata={"spatial_reference": spatial_reference})


class Connector:
    def __init__(self, *pages):
        self.pages = iter(pages)
        self.calls = []

    def fetch_page(self, checkpoint=None):
        self.calls.append(checkpoint)
        return next(self.pages)


def test_valid_page_preserves_native_status_and_checkpoint():
    original = envelope([row()], offset=1)
    snapshot = deepcopy(original)
    connector = Connector(original)
    guarded = worker.ContextConnectorGuard(connector)
    assert guarded.fetch_page({"offset": 0}) is original
    assert original == snapshot
    assert original.records[0]["Status"] == "IN REVIEW"
    assert "approval_stage" not in original.records[0]
    assert connector.calls == [{"offset": 0}]


@pytest.mark.parametrize("centroid", [
    None, {}, {"x": -82.14}, {"y": 29.18},
    {"x": float("nan"), "y": 29.18}, {"x": -82.14, "y": float("inf")},
    {"x": float("-inf"), "y": 29.18}, {"x": "-82.14", "y": 29.18},
    {"x": -82.14, "y": True}, {"x": 600000, "y": 1700000},
    {"x": -181, "y": 29.18}, {"x": -82.14, "y": 91},
    {"x": -74.99, "y": 29.18}, {"x": -90.01, "y": 29.18},
    {"x": -82.14, "y": 19.99}, {"x": -82.14, "y": 35.01},
])
def test_invalid_axes_rejected_before_page_return(centroid):
    page = envelope([row(centroid=centroid)], spatial_reference={"wkid": 4326})
    guarded = worker.ContextConnectorGuard(Connector(page))
    with pytest.raises(ValueError):
        guarded.fetch_page()
    assert guarded.identities == set()


@pytest.mark.parametrize("wkid", [None, 2237, 3857, "4326", True])
def test_wrong_or_missing_spatial_reference_rejected(wkid):
    page = envelope([row(centroid={"x": -82.14, "y": 29.18,
                                  "spatialReference": {"wkid": wkid}})])
    with pytest.raises(ValueError):
        worker.ContextConnectorGuard(Connector(page)).fetch_page()


def test_envelope_wgs84_fallback_and_centroid_conflict():
    page = envelope([row(centroid={"x": -82.14, "y": 29.18})],
                    spatial_reference={"wkid": 4326})
    assert worker.ContextConnectorGuard(Connector(page)).fetch_page() is page
    conflict = envelope([row(centroid={"x": -82.14, "y": 29.18,
                                      "spatialReference": {"wkid": 2237}})],
                        spatial_reference={"wkid": 4326})
    with pytest.raises(ValueError):
        worker.ContextConnectorGuard(Connector(conflict)).fetch_page()


@pytest.mark.parametrize("field", ["Description", "owner_name", "email", "geometry", "_geometry"])
def test_extra_fields_fail_closed_without_echoing_private_values(field):
    private = "Synthetic Private Person private@example.test"
    page = envelope([row(), row("SYNTHETIC-2", **{field: private})])
    guarded = worker.ContextConnectorGuard(Connector(page))
    with pytest.raises(ValueError) as error:
        guarded.fetch_page()
    assert private not in str(error.value)
    assert guarded.identities == set()  # No earlier row in the same page was released.


@pytest.mark.parametrize("identity", [None, "", "  ", 123, True])
def test_permit_identity_must_be_nonblank_text(identity):
    with pytest.raises(ValueError):
        worker.ContextConnectorGuard(Connector(envelope([row(identity)]))).fetch_page()


def test_duplicate_ids_within_page_and_across_pages_are_rejected():
    within = worker.ContextConnectorGuard(Connector(envelope([row(), row()])))
    with pytest.raises(ValueError):
        within.fetch_page()
    assert within.identities == set()
    first = envelope([row()], offset=1)
    across = worker.ContextConnectorGuard(Connector(first, envelope([row()])))
    across.fetch_page()
    with pytest.raises(ValueError):
        across.fetch_page(first.checkpoint)
    assert across.identities == {"SYNTHETIC-1"}


def test_exact_ceiling_accepts_four_pages_then_empty_exhaustion_probe():
    pages = [envelope([row(f"SYNTHETIC-{i}") for i in range(start, start + 250)],
                      offset=start + 250) for start in range(0, 1000, 250)]
    terminal = envelope()
    connector = Connector(*pages, terminal)
    guarded = worker.ContextConnectorGuard(connector)
    checkpoint = None
    seen = 0
    for _ in range(5):
        page = guarded.fetch_page(checkpoint)
        seen += len(page.records)
        checkpoint = page.checkpoint
    assert page is terminal and not page.has_more
    assert seen == len(guarded.identities) == 1000
    assert connector.calls[-1] == {"offset": 1000}


@pytest.mark.parametrize("prior_count", [999, 1000])
def test_record_1001_not_released_and_ceiling_state_is_atomic(prior_count):
    first = envelope([row(f"SYNTHETIC-{i}") for i in range(prior_count)], offset=prior_count)
    overflowing = envelope([row(f"SYNTHETIC-{i}") for i in range(prior_count, 1001)])
    guarded = worker.ContextConnectorGuard(Connector(first, overflowing))
    guarded.fetch_page()
    with pytest.raises(ValueError, match="ceiling"):
        guarded.fetch_page(first.checkpoint)
    assert len(guarded.identities) == prior_count


def test_context_factory_is_scoped_and_restored_after_error(monkeypatch):
    connector = Connector(envelope([row()]))
    calls = []

    def factory(adapter, config):
        calls.append((adapter, config))
        return connector

    monkeypatch.setattr(service, "build_connector", factory)
    source = SimpleNamespace(key=worker.OCALA_CONTEXT_KEY, base_url="https://synthetic.invalid/layer/19")
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with worker.context_connector_guard(source):
            result = service.build_connector("arcgis", {"endpoint": source.base_url})
            assert isinstance(result, worker.ContextConnectorGuard)
            result.fetch_page()
            for adapter, endpoint in (("socrata", source.base_url), ("arcgis", "https://other.invalid")):
                with pytest.raises(ValueError):
                    service.build_connector(adapter, {"endpoint": endpoint})
            raise RuntimeError("synthetic failure")
    assert service.build_connector is factory
    assert len(calls) == 1
    with worker.context_connector_guard(SimpleNamespace(key="other-source")):
        assert service.build_connector is factory
    assert service.build_connector is factory
