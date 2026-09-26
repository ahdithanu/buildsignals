from __future__ import annotations

import pytest

from app.services.ingestion.external_references import extract_external_references


def test_url_reference_requires_an_allowlisted_exact_host():
    settings = {
        "external_reference_extractors": [
            {
                "source_field": "legislative_url",
                "namespace": "legistar:test:legislation",
                "transform": "url_query_parameter",
                "parameter": "ID",
                "allowed_hosts": ["city.legistar.com"],
            }
        ]
    }

    assert extract_external_references(
        {"legislative_url": "https://city.legistar.com/LegislationDetail.aspx?ID=155772"},
        settings,
    )[0].normalized_value == "155772"
    assert extract_external_references(
        {"legislative_url": "https://city.legistar.com.evil.test/?ID=155772"},
        settings,
    ) == ()


def test_invalid_external_reference_transform_fails_closed():
    with pytest.raises(ValueError, match="unsupported external reference transform"):
        extract_external_references(
            {"matter": "155772"},
            {
                "external_reference_extractors": [
                    {
                        "source_field": "matter",
                        "namespace": "legistar:test:legislation",
                        "transform": "fuzzy_url_guess",
                    }
                ]
            },
        )


def test_regex_reference_extracts_an_exact_project_identity():
    references = extract_external_references(
        {"title": "P25-001-A1 Wilson Groves master sign program"},
        {
            "external_reference_extractors": [
                {
                    "source_field": "title",
                    "namespace": "psl:planning_project",
                    "transform": "regex_extract",
                    "pattern": r"\b(P[0-9]{2}-[0-9]{3}(?:-A[0-9]+)?)\b",
                    "group": 1,
                }
            ]
        },
    )

    assert references[0].normalized_value == "p25-001-a1"
    assert references[0].source_field == "title"


@pytest.mark.parametrize(
    ("pattern", "group", "message"),
    [
        ("[", 0, "regex pattern is invalid"),
        (r"(P[0-9]+)", 2, "regex group does not exist"),
    ],
)
def test_invalid_regex_reference_configuration_fails_closed(pattern, group, message):
    with pytest.raises(ValueError, match=message):
        extract_external_references(
            {"title": "P123"},
            {
                "external_reference_extractors": [
                    {
                        "source_field": "title",
                        "namespace": "psl:planning_project",
                        "transform": "regex_extract",
                        "pattern": pattern,
                        "group": group,
                    }
                ]
            },
        )
