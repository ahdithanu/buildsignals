from __future__ import annotations

from typing import Any, Mapping

import pytest

from app.services.ingestion.connectors import LegistarPlanningConnector, build_connector
from app.services.ingestion.connectors.base import (
    ConnectorResponseError,
    InvalidCheckpointError,
)

ENDPOINT = "https://webapi.legistar.com/v1/dallastx"


class FakeHttpClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, Mapping[str, Any], Mapping[str, str]]] = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, params or {}, headers or {}))
        return next(self.responses)


def _event(
    event_id: int,
    *,
    body: str = "City Plan Commission",
    event_date: str = "2026-09-03T00:00:00",
    minutes_published: str | None = None,
) -> dict[str, Any]:
    return {
        "EventId": event_id,
        "EventGuid": f"event-guid-{event_id}",
        "EventBodyName": body,
        "EventDate": event_date,
        "EventTime": "9:00 AM",
        "EventAgendaLastPublishedUTC": "2026-08-20T15:10:00Z",
        "EventMinutesLastPublishedUTC": minutes_published,
        "EventLastModifiedUtc": "2026-09-04T19:00:00Z",
        "EventInSiteURL": f"https://dallastx.legistar.com/MeetingDetail.aspx?ID={event_id}",
    }


def _item(
    item_id: int,
    *,
    title: str,
    agenda_note: str | None = None,
    minutes_note: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    return {
        "EventItemId": item_id,
        "EventItemGuid": f"item-guid-{item_id}",
        "EventItemAgendaNumber": "5",
        "EventItemTitle": title,
        "EventItemMatterId": 8871,
        "EventItemMatterFile": "Z212-314",
        "EventItemMatterName": "Retail development and site plan",
        "EventItemAgendaNote": agenda_note,
        "EventItemMinutesNote": minutes_note,
        "EventItemActionName": action,
        "EventItemInSiteURL": (
            "https://dallastx.legistar.com/LegislationDetail.aspx?ID=8871"
        ),
        # A defensive fixture: this must never leak even if an upstream response
        # disregards EventItemAttachments=0.
        "EventItemAttachments": [{"Attachment": "BASE64-BINARY-MUST-NOT-LEAK"}],
    }


def _detail(event: Mapping[str, Any], items: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {**event, "EventItems": items}


def test_emits_canonical_agenda_and_decision_rows_without_attachments():
    agenda_event = _event(42)
    decision_event = _event(43, minutes_published="2026-09-04T18:30:00Z")
    scheduled = _item(
        4201,
        title="Toll Brothers mixed-use development at Preston Road",
        agenda_note="Public hearing to consider a new planned development district.",
    )
    decided = _item(
        4202,
        title="Costco warehouse zoning case",
        agenda_note="Public hearing on zoning case Z212-314.",
        minutes_note="Commission recommended approval subject to the staff conditions.",
        action="Recommended for Approval",
    )
    http = FakeHttpClient(
        [
            [agenda_event, decision_event],
            _detail(agenda_event, [scheduled]),
            _detail(decision_event, [decided]),
        ]
    )
    connector = LegistarPlanningConnector(
        ENDPOINT,
        page_size=10,
        event_page_size=25,
        max_events=10,
        max_items_per_event=10,
        max_records=20,
        http_client=http,
    )

    rows = connector.fetch().records

    assert len(rows) == 2
    agenda, decision = rows
    assert agenda["source_record_id"].startswith("legistar:")
    assert agenda["source_record_id"].endswith(":42:4201")
    assert agenda["legistar_event_id"] == 42
    assert agenda["legistar_event_item_id"] == 4201
    assert agenda["event_type"] == "planning_hearing_agenda_item"
    assert agenda["stage"] == "hearing_scheduled"
    assert agenda["reference_number"] == "Z212-314"
    assert agenda["legistar_matter_id"] == 8871
    assert agenda["agenda_item_number"] == "5"
    assert agenda["governing_body"] == "City Plan Commission"
    assert agenda["meeting_date"] == "2026-09-03"
    assert agenda["meeting_at"].startswith("2026-09-03")
    assert agenda["published_at"] == "2026-08-20T15:10:00Z"
    assert agenda["modified_at"] == "2026-09-04T19:00:00Z"
    assert agenda["source_url"].endswith("LegislationDetail.aspx?ID=8871")
    assert "Public hearing" in agenda["evidence_excerpt"]

    assert decision["source_record_id"].endswith(":43:4202")
    assert decision["event_type"] == "planning_hearing_decision"
    assert decision["stage"] == "decision_recorded"
    assert decision["published_at"] == "2026-09-04T18:30:00Z"
    assert "recommended approval" in decision["evidence_excerpt"].casefold()
    assert "Recommended for Approval" in decision["evidence_excerpt"]

    assert "EventItemAttachments" not in agenda
    assert "EventItemAttachments" not in decision
    assert "BASE64-BINARY-MUST-NOT-LEAK" not in repr(rows)
    detail_call = http.calls[1]
    assert detail_call[0] == f"{ENDPOINT}/Events/42"
    assert detail_call[1] == {
        "EventItems": 1,
        "AgendaNote": 1,
        "MinutesNote": 1,
        "EventItemAttachments": 0,
    }


def test_stable_identity_does_not_change_when_item_text_changes():
    event = _event(42)
    original = _item(4201, title="Initial title", agenda_note="Initial agenda note")
    revised = _item(4201, title="Revised title", agenda_note="Revised agenda note")

    first = LegistarPlanningConnector(
        ENDPOINT,
        http_client=FakeHttpClient([[event], _detail(event, [original])]),
    ).fetch()
    second = LegistarPlanningConnector(
        ENDPOINT,
        http_client=FakeHttpClient([[event], _detail(event, [revised])]),
    ).fetch()

    assert first.records[0]["source_record_id"] == second.records[0]["source_record_id"]


def test_output_checkpoint_pages_cached_records_without_refetching():
    event = _event(42)
    items = [
        _item(4201, title="First public item", agenda_note="First evidence"),
        _item(4202, title="Second public item", agenda_note="Second evidence"),
        _item(4203, title="Third public item", agenda_note="Third evidence"),
    ]
    http = FakeHttpClient([[event], _detail(event, items)])
    connector = LegistarPlanningConnector(
        ENDPOINT,
        page_size=2,
        max_records=10,
        http_client=http,
    )

    first = connector.fetch()
    second = connector.fetch(first.checkpoint)

    assert [row["legistar_event_item_id"] for row in first.records] == [4201, 4202]
    assert first.checkpoint == {"offset": 2}
    assert first.has_more is True
    assert [row["legistar_event_item_id"] for row in second.records] == [4203]
    assert second.checkpoint is None
    assert second.has_more is False
    assert len(http.calls) == 2

    with pytest.raises(InvalidCheckpointError):
        connector.fetch({"offset": -1})


def test_event_discovery_uses_bounded_odata_paging_and_body_filter():
    first_events = [
        _event(42, body="City Plan Commission"),
        _event(43, body="City Council"),
    ]
    final_events = [_event(44, body="City Plan Commission")]
    http = FakeHttpClient(
        [
            first_events,
            _detail(first_events[0], [_item(4201, title="One", agenda_note="Evidence")]),
            _detail(first_events[1], [_item(4301, title="Two", agenda_note="Evidence")]),
            final_events,
            _detail(final_events[0], [_item(4401, title="Three", agenda_note="Evidence")]),
        ]
    )
    connector = LegistarPlanningConnector(
        ENDPOINT,
        page_size=10,
        event_page_size=2,
        max_events=3,
        max_records=10,
        body_names=["City Plan Commission", "City Council"],
        lookback_days=30,
        future_days=120,
        http_client=http,
    )

    rows = connector.fetch().records

    assert [row["legistar_event_id"] for row in rows] == [42, 43, 44]
    event_calls = [call for call in http.calls if call[0] == f"{ENDPOINT}/Events"]
    assert [call[1]["$skip"] for call in event_calls] == [0, 2]
    assert [call[1]["$top"] for call in event_calls] == [2, 1]
    assert all("EventDate" in call[1]["$filter"] for call in event_calls)
    assert all("City Plan Commission" in call[1]["$filter"] for call in event_calls)
    assert all("City Council" in call[1]["$filter"] for call in event_calls)
    assert all("EventId" in call[1]["$orderby"] for call in event_calls)


def test_filters_unrequested_bodies_even_if_api_returns_them():
    requested = _event(42, body="City Plan Commission")
    unrelated = _event(43, body="Employee Retirement Fund Board")
    http = FakeHttpClient(
        [
            [requested, unrelated],
            _detail(requested, [_item(4201, title="Public case", agenda_note="Evidence")]),
        ]
    )
    connector = LegistarPlanningConnector(
        ENDPOINT,
        body_names=["city plan commission"],
        http_client=http,
    )

    rows = connector.fetch().records

    assert [row["legistar_event_id"] for row in rows] == [42]
    assert all(call[0] != f"{ENDPOINT}/Events/43" for call in http.calls)


@pytest.mark.parametrize(
    ("responses", "message"),
    [
        (["not a list"], "events.*list"),
        ([[{"EventBodyName": "City Plan Commission"}]], "EventId"),
        ([[_event(42)], {**_event(42), "EventItems": "not a list"}], "event items.*list"),
        ([[_event(42)], {**_event(42), "EventItems": [{"EventItemTitle": "No id"}]}], "EventItemId"),
    ],
)
def test_rejects_malformed_legistar_payloads(responses, message):
    connector = LegistarPlanningConnector(ENDPOINT, http_client=FakeHttpClient(responses))

    with pytest.raises(ConnectorResponseError, match=message):
        connector.fetch()


def test_hard_limits_bound_events_items_and_records():
    first = _event(42)
    http = FakeHttpClient(
        [
            [first],
            _detail(
                first,
                [
                    _item(4201, title="Allowed", agenda_note="Evidence"),
                ],
            ),
        ]
    )
    connector = LegistarPlanningConnector(
        ENDPOINT,
        event_page_size=50,
        max_events=1,
        max_items_per_event=1,
        max_records=1,
        http_client=http,
    )

    result = connector.fetch()

    assert [row["legistar_event_item_id"] for row in result.records] == [4201]
    assert http.calls[0][1]["$top"] == 1
    assert all(call[0] != f"{ENDPOINT}/Events/43" for call in http.calls)


def test_rejects_event_payload_above_item_limit():
    event = _event(42)
    connector = LegistarPlanningConnector(
        ENDPOINT,
        max_items_per_event=1,
        http_client=FakeHttpClient(
            [
                [event],
                _detail(
                    event,
                    [
                        _item(4201, title="One", agenda_note="Evidence"),
                        _item(4202, title="Two", agenda_note="Evidence"),
                    ],
                ),
            ]
        ),
    )

    with pytest.raises(ConnectorResponseError, match="configured maximum is 1"):
        connector.fetch()


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"event_page_size": 0}, "event_page_size"),
        ({"max_events": 0}, "max_events"),
        ({"max_items_per_event": 0}, "max_items_per_event"),
        ({"max_records": 0}, "max_records"),
        ({"lookback_days": -1}, "lookback_days"),
        ({"future_days": -1}, "future_days"),
    ],
)
def test_rejects_invalid_bounds(kwargs, field):
    with pytest.raises(ValueError, match=field):
        LegistarPlanningConnector(ENDPOINT, **kwargs)


def test_factory_registers_legistar_adapter_and_package_export(monkeypatch):
    fake_http = FakeHttpClient([])
    monkeypatch.setattr(
        "app.services.ingestion.connectors.factory.RetryingHttpClient",
        lambda **_kwargs: fake_http,
    )

    connector = build_connector(
        "legistar",
        {
            "endpoint": ENDPOINT,
            "page_size": 25,
            "event_page_size": 50,
            "max_events": 200,
            "max_items_per_event": 75,
            "max_records": 500,
            "body_names": ["City Plan Commission", "City Council"],
            "lookback_days": 45,
            "future_days": 180,
        },
    )

    assert isinstance(connector, LegistarPlanningConnector)
    assert connector.source_name == "legistar"
    assert connector.page_size == 25
    assert connector.event_page_size == 50
    assert connector.max_events == 200
    assert connector.max_items_per_event == 75
    assert connector.max_records == 500
    assert connector.body_names == ("City Plan Commission", "City Council")
    assert connector.lookback_days == 45
    assert connector.future_days == 180
    assert connector.http_client is fake_http
