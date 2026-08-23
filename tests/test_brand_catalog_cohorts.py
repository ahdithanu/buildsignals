from __future__ import annotations

import re
import unicodedata

from app.services.brand_intelligence import load_brand_catalog

EXPECTED_MAJOR_BUILDERS = {
    "toll_brothers",
    "dr_horton",
    "lennar",
    "pultegroup",
    "nvr_ryan_homes",
    "kb_home",
    "taylor_morrison",
    "meritage_homes",
    "century_communities",
    "mi_homes",
    "tri_pointe_homes",
    "dream_finders_homes",
}
BUILDER_CONTEXT_TERMS = {
    "builder",
    "home builder",
    "homebuilder",
    "residential development",
    "subdivision",
    "single-family homes",
}


def _normalize_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def test_toll_brothers_uses_conservative_corporate_aliases():
    toll = next(entry for entry in load_brand_catalog() if entry.key == "toll_brothers")

    assert {alias.alias for alias in toll.aliases} == {
        "Toll Brothers",
        "Toll Brothers, Inc.",
    }
    assert all(not alias.requires_context for alias in toll.aliases)


def test_commercial_cohorts_are_bounded_and_tagged():
    catalog = load_brand_catalog()
    national_retail = [
        entry for entry in catalog if entry.attributes.get("signal_cohort") == "national_retail"
    ]
    major_builders = [
        entry for entry in catalog if entry.attributes.get("signal_cohort") == "major_builder"
    ]

    assert len(national_retail) == 102
    assert {entry.key for entry in major_builders} == EXPECTED_MAJOR_BUILDERS
    assert all("national_retail" in entry.attributes["watchlist_tags"] for entry in national_retail)
    assert all(
        "retail_expansion" in entry.attributes["watchlist_tags"] for entry in national_retail
    )
    assert all(entry.category in entry.attributes["watchlist_tags"] for entry in national_retail)
    assert all(entry.scale == "national" for entry in major_builders)
    assert all(entry.priority == 5 for entry in major_builders)
    assert all(
        {"major_builder", "homebuilder", "residential_development"}
        <= set(entry.attributes["watchlist_tags"])
        for entry in major_builders
    )


def test_catalog_aliases_are_unique_after_normalization():
    aliases = [
        _normalize_alias(alias.alias) for entry in load_brand_catalog() for alias in entry.aliases
    ]

    assert len(aliases) == len(set(aliases))


def test_ambiguous_short_builder_aliases_require_builder_context():
    builders = [
        entry
        for entry in load_brand_catalog()
        if entry.attributes.get("signal_cohort") == "major_builder"
    ]
    short_aliases = [
        alias
        for entry in builders
        for alias in entry.aliases
        if len(_normalize_alias(alias.alias).replace(" ", "")) <= 3
    ]

    assert [alias.alias for alias in short_aliases] == ["NVR"]
    assert short_aliases[0].requires_context is True
    assert BUILDER_CONTEXT_TERMS <= set(short_aliases[0].context_terms)
    assert not any(
        alias.alias.casefold() in {"dr", "kb", "mi", "tri"}
        for entry in builders
        for alias in entry.aliases
    )
