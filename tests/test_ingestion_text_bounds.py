from app.services.graph_service import normalize_name
from app.services.ingestion.normalization import normalize_permit, normalize_planning_record
from app.services.ingestion.service import _graph_label


def test_oversize_parcel_reference_is_preserved_but_not_used_as_identity():
    value = "123-456;" * 70
    raw = {"id": "permit-1", "parcel": value}
    normalized = normalize_permit(raw, {"id": "source_record_id", "parcel": "parcel_id"})
    assert normalized.values["source_record_id"] == "permit-1"
    assert normalized.values["parcel_id"] is None
    assert normalized.unmapped["unresolved_canonical_fields"]["parcel_id"] == value
    assert raw["parcel"] == value


def test_long_planning_title_retains_full_original_evidence():
    title = "Planning agenda item " * 120
    raw = {"id": "matter-1", "title": title}
    result = normalize_planning_record(raw, {"id": "source_record_id", "title": "title"})
    assert len(result.values["title"]) == 1000
    assert result.unmapped["original_title"] == title.strip()
    assert result.values["source_record_id"] == "matter-1"
    assert raw["title"] == title


def test_graph_labels_are_bounded_stable_and_do_not_merge_shared_prefixes():
    first, second = "Project " * 80 + "A", "Project " * 80 + "B"
    assert _graph_label(first) != _graph_label(second)
    assert _graph_label(first) == _graph_label(first)
    assert len(_graph_label(first)) <= 255
    assert len(normalize_name(_graph_label("&" * 200))) <= 255
    assert _graph_label("Small project") == "Small project"
