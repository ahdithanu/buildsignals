from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from app.schemas.ingestion import IngestionSourceCreate


@dataclass(frozen=True)
class SourceHostRequirement:
    source_key: str
    source_name: str
    jurisdiction: str | None
    url: str
    host: str
    purpose: str


@dataclass(frozen=True)
class UnsafeSourceUrl:
    source_key: str
    url: str
    reason: str


@dataclass(frozen=True)
class IngestionHostPolicyReport:
    ready: bool
    coverage_ready: bool
    policy_digest: str
    source_count: int
    required_host_count: int
    configured_host_count: int
    required_hosts: list[str]
    configured_hosts: list[str]
    missing_hosts: list[str]
    unused_hosts: list[str]
    unsafe_sources: list[UnsafeSourceUrl]
    requirements: list[SourceHostRequirement]


def configured_ingestion_hosts(value: str | None = None) -> frozenset[str]:
    raw = os.environ.get("INGESTION_ALLOWED_HOSTS", "") if value is None else value
    hosts: set[str] = set()
    for item in raw.split(","):
        if not item.strip():
            continue
        hosts.add(_normalize_configured_host(item))
    return frozenset(hosts)


def audit_ingestion_hosts(
    entries: Iterable[IngestionSourceCreate],
    *,
    allowed_hosts: str | Iterable[str] | None = None,
) -> IngestionHostPolicyReport:
    entry_list = list(entries)
    if isinstance(allowed_hosts, str) or allowed_hosts is None:
        configured = configured_ingestion_hosts(allowed_hosts)
    else:
        configured = frozenset(_normalize_configured_host(host) for host in allowed_hosts)

    requirements: list[SourceHostRequirement] = []
    unsafe: list[UnsafeSourceUrl] = []
    for entry in entry_list:
        try:
            urls = source_urls(entry)
        except ValueError as exc:
            unsafe.append(UnsafeSourceUrl(
                entry.key, redact_source_url(entry.base_url or ""), str(exc)
            ))
            continue
        for purpose, url in urls:
            try:
                host = safe_source_host(url, require_https=True)
            except ValueError as exc:
                unsafe.append(UnsafeSourceUrl(
                    entry.key, redact_source_url(url), f"{purpose}: {exc}"
                ))
                continue
            requirements.append(SourceHostRequirement(
                source_key=entry.key,
                source_name=entry.name,
                jurisdiction=entry.jurisdiction,
                url=redact_source_url(url),
                host=host,
                purpose=purpose,
            ))

    required = frozenset(requirement.host for requirement in requirements)
    missing = sorted(
        host for host in required if not any(host_is_allowed(host, item) for item in configured)
    )
    unused = sorted(
        item for item in configured if not any(host_is_allowed(host, item) for host in required)
    )
    policy_digest = hashlib.sha256(json.dumps(
        {"configured_hosts": sorted(configured)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")).hexdigest()
    coverage_ready = not missing and not unsafe
    return IngestionHostPolicyReport(
        ready=coverage_ready and not unused,
        coverage_ready=coverage_ready,
        policy_digest=policy_digest,
        source_count=len(entry_list),
        required_host_count=len(required),
        configured_host_count=len(configured),
        required_hosts=sorted(required),
        configured_hosts=sorted(configured),
        missing_hosts=missing,
        unused_hosts=unused,
        unsafe_sources=sorted(unsafe, key=lambda item: item.source_key),
        requirements=sorted(requirements, key=lambda item: item.source_key),
    )


def effective_source_url(entry: IngestionSourceCreate) -> str:
    connector = (entry.settings or {}).get("connector") or {}
    key = "source" if entry.adapter == "csv" else "endpoint"
    override = connector.get(key)
    if isinstance(override, str) and override.strip():
        return override.strip()
    if isinstance(entry.base_url, str) and entry.base_url.strip():
        return entry.base_url.strip()
    raise ValueError(f"Catalog source {entry.key} has no effective connector URL")


def redact_source_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.hostname:
            return "<redacted-invalid-url>"
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme.lower()}://{host}{port}{parsed.path or ''}"
    except (TypeError, ValueError):
        return "<redacted-invalid-url>"


def source_urls(entry: IngestionSourceCreate) -> list[tuple[str, str]]:
    primary = effective_source_url(entry)
    settings = entry.settings or {}
    key = "source" if entry.adapter == "csv" else "endpoint"
    urls = [("primary", primary)]
    probes = settings.get("canary_stage_probes") or []
    for index, probe in enumerate(probes, start=1):
        if not isinstance(probe, dict):
            continue
        override = probe.get("connector") or {}
        if isinstance(override, dict) and isinstance(override.get(key), str):
            urls.append((str(probe.get("name") or f"stage_probe_{index}"), override[key]))
    freshness = settings.get("canary_freshness_probe") or {}
    if isinstance(freshness, dict):
        override = freshness.get("connector") or {}
        if isinstance(override, dict) and isinstance(override.get(key), str):
            urls.append(("freshness_probe", override[key]))
    return urls


def _normalize_configured_host(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if not host or "://" in host or "/" in host or "@" in host or ":" in host:
        raise ValueError(f"Invalid ingestion allowlist host: {value}")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"Invalid ingestion allowlist host: {value}") from exc
    if (
        host == "localhost"
        or host.endswith(".localhost")
        or all(char.isdigit() or char == "." for char in host)
        or host.startswith("0x")
        or "." not in host
        or host.startswith(".")
        or ".." in host
        or any(not label or label.startswith("-") or label.endswith("-") for label in host.split("."))
        or any(not char.isalnum() and char != "-" for char in host.replace(".", ""))
    ):
        raise ValueError(f"Invalid ingestion allowlist host: {value}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ValueError(f"Invalid ingestion allowlist host: {value}")


def safe_source_host(url: str, *, require_https: bool = False) -> str:
    parsed = urlparse(url)
    allowed_schemes = {"https"} if require_https else {"http", "https"}
    if parsed.scheme.lower() not in allowed_schemes or not parsed.hostname:
        expected = "HTTPS" if require_https else "HTTP or HTTPS"
        raise ValueError(f"source URL must use {expected}")
    if parsed.username or parsed.password:
        raise ValueError("source URL cannot contain credentials")
    if any(char in url for char in ("\\", "\r", "\n", "\t")):
        raise ValueError("source URL contains invalid characters")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("source URL has an invalid port") from exc
    if require_https and port not in {None, 443}:
        raise ValueError("source URL must use the standard HTTPS port")
    host = parsed.hostname.lower().rstrip(".").encode("idna").decode("ascii")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("source URL cannot target localhost")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("source URL cannot use an IP literal")
    if all(char.isdigit() or char == "." for char in host) or host.startswith("0x"):
        raise ValueError("source URL cannot use an alternate numeric IP form")
    if "." not in host:
        raise ValueError("source URL host must be a fully qualified domain name")
    return host


def host_is_allowed(host: str, allowed: str) -> bool:
    return host == allowed
