from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Pattern, Sequence

DEFAULT_MAX_ITEMS = 250
DEFAULT_MAX_ITEM_CHARACTERS = 100_000
_PATTERN_FLAGS = re.IGNORECASE | re.MULTILINE
_WHITESPACE = re.compile(r"\s+")


class PlanningItemSegmentationError(ValueError):
    """Base class for deterministic planning-item segmentation failures."""


class PlanningItemLimitError(PlanningItemSegmentationError):
    """Raised when a document exceeds configured segmentation limits."""


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class PlanningItemRules:
    item_pattern: str | Pattern[str]
    file_pattern: str | Pattern[str]
    value_patterns: Mapping[str, str | Pattern[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_named_group(self.item_pattern, "item_number", "item_pattern")
        _require_named_group(self.file_pattern, "file_number", "file_pattern")
        for field_name, pattern in self.value_patterns.items():
            if not field_name.strip():
                raise ValueError("value pattern field names cannot be empty")
            _require_named_group(pattern, "value", f"value_patterns[{field_name!r}]")


@dataclass(frozen=True)
class PlanningItem:
    identity: str
    meeting_date: date
    item_number: str
    file_numbers: tuple[str, ...]
    text: str
    values: Mapping[str, str]
    source_pages: tuple[int, ...]
    document_hash: str
    source_url: str


def segment_planning_items(
    pages: Sequence[PageText],
    *,
    meeting_date: date,
    document_hash: str,
    source_url: str,
    rules: PlanningItemRules,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_item_characters: int = DEFAULT_MAX_ITEM_CHARACTERS,
) -> tuple[PlanningItem, ...]:
    """Split page-numbered agenda or minutes text into evidence-backed project items."""
    if max_items <= 0:
        raise ValueError("max_items must be greater than zero")
    if max_item_characters <= 0:
        raise ValueError("max_item_characters must be greater than zero")
    if not document_hash.strip():
        raise ValueError("document_hash cannot be empty")
    if not source_url.strip():
        raise ValueError("source_url cannot be empty")

    item_pattern = _compile(rules.item_pattern)
    file_pattern = _compile(rules.file_pattern)
    value_patterns = {
        field_name: _compile(pattern) for field_name, pattern in rules.value_patterns.items()
    }
    document_text, page_spans = _join_pages(pages)
    item_matches = list(item_pattern.finditer(document_text))
    if len(item_matches) > max_items:
        raise PlanningItemLimitError(
            f"document contains {len(item_matches)} item sections; maximum is {max_items}"
        )

    items: list[PlanningItem] = []
    for index, item_match in enumerate(item_matches):
        start = item_match.start()
        end = (
            item_matches[index + 1].start() if index + 1 < len(item_matches) else len(document_text)
        )
        item_text = document_text[start:end].strip()
        if len(item_text) > max_item_characters:
            raise PlanningItemLimitError(
                f"item {item_match.group('item_number').strip()} contains {len(item_text)} "
                f"characters; maximum is {max_item_characters}"
            )

        file_numbers = _official_file_numbers(file_pattern, item_text)
        if not file_numbers:
            continue

        item_number = _normalize_value(item_match.group("item_number"))
        values = _extract_values(value_patterns, item_text)
        source_pages = tuple(
            page_number
            for page_number, page_start, page_end in page_spans
            if page_start < end and page_end > start
        )
        items.append(
            PlanningItem(
                identity=_stable_identity(meeting_date, item_number, file_numbers),
                meeting_date=meeting_date,
                item_number=item_number,
                file_numbers=file_numbers,
                text=item_text,
                values=values,
                source_pages=source_pages,
                document_hash=document_hash,
                source_url=source_url,
            )
        )
    return tuple(items)


def _compile(pattern: str | Pattern[str]) -> Pattern[str]:
    return re.compile(pattern, _PATTERN_FLAGS) if isinstance(pattern, str) else pattern


def _require_named_group(pattern: str | Pattern[str], group_name: str, rule_name: str) -> None:
    if group_name not in _compile(pattern).groupindex:
        raise ValueError(f"{rule_name} must define a named {group_name!r} group")


def _join_pages(pages: Sequence[PageText]) -> tuple[str, tuple[tuple[int, int, int], ...]]:
    chunks: list[str] = []
    spans: list[tuple[int, int, int]] = []
    seen_pages: set[int] = set()
    cursor = 0
    for page in pages:
        if page.page_number <= 0:
            raise ValueError("page numbers must be greater than zero")
        if page.page_number in seen_pages:
            raise ValueError(f"duplicate page number: {page.page_number}")
        seen_pages.add(page.page_number)
        if chunks:
            chunks.append("\n")
            cursor += 1
        start = cursor
        chunks.append(page.text)
        cursor += len(page.text)
        spans.append((page.page_number, start, cursor))
    return "".join(chunks), tuple(spans)


def _official_file_numbers(pattern: Pattern[str], text: str) -> tuple[str, ...]:
    numbers = {
        _normalize_file_number(match.group("file_number"))
        for match in pattern.finditer(text)
        if match.group("file_number").strip()
    }
    return tuple(sorted(numbers))


def _extract_values(patterns: Mapping[str, Pattern[str]], text: str) -> Mapping[str, str]:
    values: dict[str, str] = {}
    for field_name, pattern in patterns.items():
        match = pattern.search(text)
        if match and match.group("value").strip():
            values[field_name] = _normalize_value(match.group("value"))
    return values


def _stable_identity(meeting_date: date, item_number: str, file_numbers: tuple[str, ...]) -> str:
    identity_input = "|".join(
        (
            meeting_date.isoformat(),
            item_number.casefold(),
            *(number.casefold() for number in file_numbers),
        )
    )
    return hashlib.sha256(identity_input.encode("utf-8")).hexdigest()


def _normalize_file_number(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def _normalize_value(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()
