"""Bounded reader for public Granicus Legistar meeting items."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from .base import (
    BaseConnector,
    Checkpoint,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    RetryingHttpClient,
    checkpoint_offset,
)


class LegistarPlanningConnector(BaseConnector):
    """Emit source-neutral planning records from public Legistar event items."""

    source_name = "legistar"

    def __init__(
        self,
        endpoint: str,
        *,
        page_size: int = 100,
        event_page_size: int = 50,
        max_events: int = 250,
        max_items_per_event: int = 250,
        max_records: int = 2500,
        body_names: Sequence[str] | None = None,
        matter_types: Sequence[str] | None = None,
        record_stages: Sequence[str] | None = None,
        suppression_patterns: Sequence[str] | None = None,
        lookback_days: int = 45,
        future_days: int = 180,
        api_token: str | None = None,
        max_evidence_characters: int = 10_000,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: HttpClient | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("endpoint is required")
        for name, value in {
            "event_page_size": event_page_size,
            "max_events": max_events,
            "max_items_per_event": max_items_per_event,
            "max_records": max_records,
            "max_evidence_characters": max_evidence_characters,
        }.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name, value in {
            "lookback_days": lookback_days,
            "future_days": future_days,
        }.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

        self.endpoint = endpoint.strip().rstrip("/")
        self.client = self.endpoint.rsplit("/", 1)[-1]
        if not self.client:
            raise ValueError("endpoint must end with a Legistar client name")
        self.event_page_size = min(event_page_size, 1000)
        self.max_events = max_events
        self.max_items_per_event = max_items_per_event
        self.max_records = max_records
        self.body_names = tuple(_clean_values(body_names))
        self._body_names = {value.casefold() for value in self.body_names}
        self.matter_types = tuple(_clean_values(matter_types))
        self._matter_types = {value.casefold() for value in self.matter_types}
        self.record_stages = tuple(_clean_values(record_stages))
        unsupported_stages = set(self.record_stages) - {
            "hearing_scheduled",
            "decision_recorded",
        }
        if unsupported_stages:
            raise ValueError(
                f"unsupported record_stages: {sorted(unsupported_stages)}"
            )
        self._record_stages = set(self.record_stages)
        self.suppression_patterns = _compile_suppression_patterns(suppression_patterns)
        self.lookback_days = lookback_days
        self.future_days = future_days
        self.api_token = api_token
        self.max_evidence_characters = max_evidence_characters
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout,
            max_retries=max_retries,
        )
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._record_cache: tuple[dict[str, Any], ...] | None = None
        self._events_processed = 0

    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        offset = checkpoint_offset(checkpoint)
        if self._record_cache is None:
            records, self._events_processed = self._records()
            self._record_cache = tuple(records)
        records = self._record_cache
        page = records[offset : offset + self.page_size]
        next_offset = offset + len(page)
        has_more = next_offset < len(records)
        return FetchEnvelope(
            source=self.source_name,
            records=page,
            checkpoint={"offset": next_offset} if has_more else None,
            has_more=has_more,
            metadata={
                "endpoint": self.endpoint,
                "offset": offset,
                "total": len(records),
                "events_processed": self._events_processed,
            },
        )

    def _records(self) -> tuple[list[dict[str, Any]], int]:
        records: list[dict[str, Any]] = []
        event_offset = 0
        events_processed = 0
        while events_processed < self.max_events and len(records) < self.max_records:
            top = min(self.event_page_size, self.max_events - events_processed)
            events = self.http_client.get_json(
                f"{self.endpoint}/Events",
                params=self._event_query(top=top, skip=event_offset),
            )
            _require_object_list(events, "Legistar events response")
            if len(events) > top:
                raise ConnectorResponseError(
                    f"Legistar events response exceeded requested page size {top}"
                )
            if not events:
                break

            for event in events:
                event_id = _required_id(event, "EventId", "Legistar event")
                body_name = _text(event.get("EventBodyName"))
                events_processed += 1
                if self._body_names and body_name.casefold() not in self._body_names:
                    continue
                detail = self.http_client.get_json(
                    f"{self.endpoint}/Events/{event_id}",
                    params={
                        "EventItems": 1,
                        "AgendaNote": 1,
                        "MinutesNote": 1,
                        "EventItemAttachments": 0,
                        **self._token_query(),
                    },
                )
                if not isinstance(detail, Mapping):
                    raise ConnectorResponseError("Legistar event detail must be an object")
                detail_id = _required_id(detail, "EventId", "Legistar event detail")
                if detail_id != event_id:
                    raise ConnectorResponseError(
                        f"Legistar event detail ID {detail_id} did not match event {event_id}"
                    )
                items = detail.get("EventItems") or []
                _require_object_list(items, "Legistar event items")
                if len(items) > self.max_items_per_event:
                    raise ConnectorResponseError(
                        f"Legistar event {event_id} returned {len(items)} items; "
                        f"configured maximum is {self.max_items_per_event}"
                    )
                for item in items:
                    if self._matter_types and _text(
                        item.get("EventItemMatterType")
                    ).casefold() not in self._matter_types:
                        continue
                    record = self._record(detail, item)
                    if record is not None and (
                        not self._record_stages
                        or record["stage"] in self._record_stages
                    ):
                        records.append(record)
                    if len(records) >= self.max_records:
                        break
                if len(records) >= self.max_records:
                    break

            event_offset += len(events)
            if len(events) < top:
                break
        return records, events_processed

    def _event_query(self, *, top: int, skip: int) -> dict[str, Any]:
        now = _as_utc(self._now())
        start = (now - timedelta(days=self.lookback_days)).date().isoformat()
        end = (now + timedelta(days=self.future_days + 1)).date().isoformat()
        filters = [
            f"EventDate ge datetime'{start}'",
            f"EventDate lt datetime'{end}'",
        ]
        if self.body_names:
            body_filter = " or ".join(
                f"EventBodyName eq '{_odata_string(name)}'" for name in self.body_names
            )
            filters.append(f"({body_filter})")
        return {
            "$filter": " and ".join(filters),
            "$orderby": "EventId desc",
            "$top": top,
            "$skip": skip,
            **self._token_query(),
        }

    def _token_query(self) -> dict[str, str]:
        return {"token": self.api_token} if self.api_token else {}

    def _record(
        self,
        event: Mapping[str, Any],
        item: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        event_id = _required_id(event, "EventId", "Legistar event detail")
        item_id = _required_id(item, "EventItemId", "Legistar event item")
        title = self._suppress(
            _first_text(
                item.get("EventItemMatterName"),
                item.get("EventItemTitle"),
                item.get("EventItemMatterFile"),
            )
        )
        evidence_parts = _unique_text(
            *(self._suppress(_text(value)) for value in (
                item.get("EventItemMatterName"),
                item.get("EventItemTitle"),
                item.get("EventItemAgendaNote"),
                item.get("EventItemMinutesNote"),
                item.get("EventItemActionName"),
                item.get("EventItemActionText"),
                item.get("EventItemMatterStatus"),
            ))
        )
        if not title or not evidence_parts:
            return None
        evidence = " ".join(evidence_parts)[: self.max_evidence_characters]
        decision = any(
            _text(value)
            for value in (
                item.get("EventItemMinutesNote"),
                item.get("EventItemActionName"),
                item.get("EventItemActionText"),
                event.get("EventMinutesLastPublishedUTC"),
            )
        )
        reference = _first_text(
            item.get("EventItemMatterFile"),
            item.get("EventItemAccelaRecordId"),
        )
        matter_id = item.get("EventItemMatterId")
        if not reference and (
            isinstance(matter_id, bool) or not isinstance(matter_id, int) or matter_id <= 0
        ):
            return None
        published_at = _first_text(
            event.get(
                "EventMinutesLastPublishedUTC" if decision else "EventAgendaLastPublishedUTC"
            ),
            item.get("EventItemLastModifiedUtc"),
            event.get("EventLastModifiedUtc"),
        )
        return {
            "source_record_id": f"legistar:{self.client}:{event_id}:{item_id}",
            "event_type": (
                "planning_hearing_decision" if decision else "planning_hearing_agenda_item"
            ),
            "stage": "decision_recorded" if decision else "hearing_scheduled",
            "title": title,
            "summary": evidence,
            "evidence_excerpt": evidence[:1000],
            "agenda_item_number": _first_text(
                item.get("EventItemAgendaNumber"),
                item.get("EventItemAgendaSequence"),
            ),
            "meeting_name": _text(event.get("EventBodyName")) or None,
            "governing_body": _text(event.get("EventBodyName")) or None,
            "meeting_date": _date_part(event.get("EventDate")),
            "meeting_at": _text(event.get("EventDate")) or None,
            "published_at": published_at or None,
            "modified_at": _first_text(
                item.get("EventItemLastModifiedUtc"),
                event.get("EventLastModifiedUtc"),
            ) or None,
            "decision_at": published_at if decision else None,
            "source_url": _first_text(
                item.get("EventItemInSiteURL"),
                event.get("EventInSiteURL"),
            ) or None,
            "reference_number": reference or None,
            "legistar_event_id": event_id,
            "legistar_event_item_id": item_id,
            "legistar_matter_id": matter_id,
            "matter_type": _text(item.get("EventItemMatterType")) or None,
            "matter_status": _text(item.get("EventItemMatterStatus")) or None,
            "action_name": _text(item.get("EventItemActionName")) or None,
            "meeting_location": _text(event.get("EventLocation")) or None,
            "event_time": _text(event.get("EventTime")) or None,
        }

    def _suppress(self, value: str) -> str:
        for pattern in self.suppression_patterns:
            value = pattern.sub("[suppressed]", value)
        return _text(value)


def _require_object_list(value: Any, label: str) -> None:
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise ConnectorResponseError(f"{label} must be a list of objects")


def _required_id(value: Mapping[str, Any], field: str, label: str) -> int:
    identifier = value.get(field)
    if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier <= 0:
        raise ConnectorResponseError(f"{label} is missing a positive {field}")
    return identifier


def _clean_values(values: Sequence[str] | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError("filter values must be a sequence of non-empty strings")
    return list(dict.fromkeys(value.strip() for value in values))


def _compile_suppression_patterns(
    values: Sequence[str] | None,
) -> tuple[re.Pattern[str], ...]:
    patterns: list[re.Pattern[str]] = []
    for value in _clean_values(values):
        try:
            patterns.append(re.compile(value, re.IGNORECASE | re.MULTILINE))
        except re.error as exc:
            raise ValueError("suppression_patterns contains an invalid regular expression") from exc
    return tuple(patterns)


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _first_text(*values: Any) -> str:
    return next((text for value in values if (text := _text(value))), "")


def _unique_text(*values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            result.append(text)
    return result


def _odata_string(value: str) -> str:
    return value.replace("'", "''")


def _date_part(value: Any) -> str | None:
    text = _text(value)
    return text[:10] if len(text) >= 10 else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
