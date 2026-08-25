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
