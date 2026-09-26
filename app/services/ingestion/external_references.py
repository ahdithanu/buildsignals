"""Source-configured exact identifiers for cross-record reconciliation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class ExtractedExternalReference:
    namespace: str
    normalized_value: str
    source_field: str
    source_url: str | None = None


def extract_external_references(
    payload: Mapping[str, Any],
    settings: Mapping[str, Any] | None,
) -> tuple[ExtractedExternalReference, ...]:
    """Extract only identifiers explicitly declared by the source configuration."""
    if not settings:
        return ()
    extractors = settings.get("external_reference_extractors")
    if extractors is None:
        return ()
    if not isinstance(extractors, list):
        raise ValueError("external_reference_extractors must be a list")

    references: dict[tuple[str, str], ExtractedExternalReference] = {}
    for extractor in extractors:
        if not isinstance(extractor, Mapping):
            raise ValueError("external reference extractor must be an object")
        source_field = _required_text(extractor, "source_field")
        namespace = _required_text(extractor, "namespace").casefold()
        transform = str(extractor.get("transform") or "scalar").strip().casefold()
        source_value = payload.get(source_field)
        if source_value is None or isinstance(source_value, (dict, list, tuple, set)):
            continue

        source_url: str | None = None
        if transform == "scalar":
            value = _normalize_value(source_value)
        elif transform == "url_query_parameter":
            parameter = _required_text(extractor, "parameter")
            source_url = str(source_value).strip()
            value = _url_query_value(source_url, parameter, extractor.get("allowed_hosts"))
        elif transform == "regex_extract":
            value = _regex_value(source_value, extractor)
        else:
            raise ValueError(f"unsupported external reference transform: {transform}")

        if not value:
            continue
        reference = ExtractedExternalReference(
            namespace=namespace,
            normalized_value=value,
            source_field=source_field,
            source_url=source_url,
        )
        references[(namespace, value)] = reference
    return tuple(references.values())


def _url_query_value(
    value: str,
    parameter: str,
    allowed_hosts: Any,
) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return None
    hosts = _allowed_hosts(allowed_hosts)
    if hosts and parsed.hostname.casefold() not in hosts:
        return None
    parameters = parse_qs(parsed.query, keep_blank_values=False)
    matched = next(
        (values for key, values in parameters.items() if key.casefold() == parameter.casefold()),
        None,
    )
    return _normalize_value(matched[0]) if matched else None


def _allowed_hosts(value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list) or not all(
        isinstance(host, str) and host.strip() for host in value
    ):
        raise ValueError("external reference allowed_hosts must be a non-empty string list")
    return {host.strip().casefold() for host in value}


def _regex_value(value: Any, extractor: Mapping[str, Any]) -> str | None:
    pattern_text = _required_text(extractor, "pattern")
    try:
        pattern = re.compile(pattern_text, re.IGNORECASE)
    except re.error as exc:
        raise ValueError("external reference regex pattern is invalid") from exc
    group = extractor.get("group", 0)
    if isinstance(group, bool) or not isinstance(group, (int, str)):
        raise ValueError("external reference regex group must be an integer or string")
    match = pattern.search(str(value)[:10_000])
    if not match:
        return None
    try:
        return _normalize_value(match.group(group))
    except (IndexError, KeyError) as exc:
        raise ValueError("external reference regex group does not exist") from exc


def _required_text(value: Mapping[str, Any], field: str) -> str:
    candidate = value.get(field)
    if not isinstance(candidate, str) or not candidate.strip():
        raise ValueError(f"external reference extractor {field} must be a non-empty string")
    return candidate.strip()


def _normalize_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    normalized = " ".join(str(value).split()).casefold()
    return normalized[:500] or None
