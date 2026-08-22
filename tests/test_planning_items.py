from __future__ import annotations

from datetime import date

import pytest

from app.services.ingestion.planning_items import (
    PageText,
    PlanningItemLimitError,
    PlanningItemRules,
    segment_planning_items,
)

SAN_JOSE_RULES = PlanningItemRules(
    item_pattern=r"^Item\s+(?P<item_number>\d+(?:\.\d+)?)\b",
    file_pattern=r"\b(?P<file_number>(?:SP|ER|H)\d{2}-\d{3})\b",
    value_patterns={
        "address": r"^Location:\s*(?P<value>.+)$",
        "owner": r"^Owner:\s*(?P<value>.+)$",
        "recommendation": r"^Recommendation:\s*(?P<value>.+)$",
    },
)


def test_segments_san_jose_items_and_retains_page_evidence():
    pages = [
        PageText(
            page_number=3,
            text="""Item 3.1
File Nos. SP26-005 and ER26-024
Special Use Permit for a retaining wall on a 0.24-acre site.
Location: 6763 Crystal Springs Drive
Owner: Robert and Leslie Chen
Recommendation: Approve""",
        ),
        PageText(
            page_number=4,
            text="""Item 3.2
File Nos. H23-014 and ER23-138
Site Development Permit for a seven-story, 264-unit multifamily building
on a 2.97-acre site.
Location: 741 South Winchester Boulevard
Owner: SYUFY Enterprises
Recommendation: Approve""",
        ),
    ]

    items = segment_planning_items(
        pages,
        meeting_date=date(2026, 8, 19),
        document_hash="agenda-sha256",
        source_url="https://example.test/2026-08-19-agenda.pdf",
        rules=SAN_JOSE_RULES,
    )

    assert len(items) == 2
    assert items[0].item_number == "3.1"
    assert items[0].file_numbers == ("SP26-005", "ER26-024")
    assert items[0].reference_number == "SP26-005"
    assert items[0].values["address"] == "6763 Crystal Springs Drive"
    assert items[0].source_pages == (3,)
    assert items[1].file_numbers == ("H23-014", "ER23-138")
    assert items[1].reference_number == "H23-014"
    assert items[1].values["owner"] == "SYUFY Enterprises"
    assert items[1].source_pages == (4,)
    assert items[1].document_hash == "agenda-sha256"


def test_agenda_and_minutes_share_identity_despite_different_wording():
    agenda = segment_planning_items(
        [PageText(4, "Item 3.2\nFiles H23-014 / ER23-138\nRecommendation: Approve")],
        meeting_date=date(2026, 8, 19),
        document_hash="agenda-hash",
        source_url="https://example.test/agenda.pdf",
        rules=SAN_JOSE_RULES,
    )[0]
    minutes = segment_planning_items(
        [PageText(2, "Item 3.2\nEnvironmental file ER23-138; permit H23-014\nAction: Approved")],
        meeting_date=date(2026, 8, 19),
        document_hash="minutes-hash",
        source_url="https://example.test/minutes.pdf",
        rules=SAN_JOSE_RULES,
    )[0]

    assert agenda.identity == minutes.identity
    assert agenda.document_hash != minutes.document_hash
    assert agenda.source_url != minutes.source_url


def test_skips_non_project_sections_without_official_file_numbers():
    items = segment_planning_items(
        [
            PageText(1, "Item 1\nCall to order and roll call"),
            PageText(2, "Item 2\nFile SP26-005\nLocation: 6763 Crystal Springs Drive"),
        ],
        meeting_date=date(2026, 8, 19),
        document_hash="hash",
        source_url="https://example.test/agenda.pdf",
        rules=SAN_JOSE_RULES,
    )

    assert [item.item_number for item in items] == ["2"]


def test_requires_named_groups_and_enforces_item_bounds():
    with pytest.raises(ValueError, match="item_number"):
        PlanningItemRules(item_pattern=r"^Item \d+", file_pattern=SAN_JOSE_RULES.file_pattern)
    with pytest.raises(ValueError, match="file_number"):
        PlanningItemRules(item_pattern=SAN_JOSE_RULES.item_pattern, file_pattern=r"SP\d+-\d+")
    with pytest.raises(ValueError, match="value"):
        PlanningItemRules(
            item_pattern=SAN_JOSE_RULES.item_pattern,
            file_pattern=SAN_JOSE_RULES.file_pattern,
            value_patterns={"owner": r"Owner: .+"},
        )

    with pytest.raises(PlanningItemLimitError, match="maximum is 1"):
        segment_planning_items(
            [PageText(1, "Item 1\nSP26-005\nItem 2\nH23-014")],
            meeting_date=date(2026, 8, 19),
            document_hash="hash",
            source_url="https://example.test/agenda.pdf",
            rules=SAN_JOSE_RULES,
            max_items=1,
        )

    with pytest.raises(PlanningItemLimitError, match="characters"):
        segment_planning_items(
            [PageText(1, "Item 1\nSP26-005\nA long description")],
            meeting_date=date(2026, 8, 19),
            document_hash="hash",
            source_url="https://example.test/agenda.pdf",
            rules=SAN_JOSE_RULES,
            max_item_characters=12,
        )
