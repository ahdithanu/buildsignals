from __future__ import annotations

import json

import pytest

from app.schemas.ingestion import IngestionSourceCreate
from app.services.ingestion import cli
from app.services.ingestion.host_policy import (
    audit_ingestion_hosts,
    configured_ingestion_hosts,
    effective_source_url,
)


def _source(
    key: str,
    base_url: str | None,
    *,
    adapter: str = "socrata",
    connector: dict | None = None,
) -> IngestionSourceCreate:
    return IngestionSourceCreate(
        key=key,
        name=key.replace("_", " ").title(),
        adapter=adapter,
        base_url=base_url,
        settings={"connector": connector or {}},
    )


def test_host_policy_reports_missing_and_unused_hosts():
    entries = [
        _source("austin", "https://data.austintexas.gov/resource/permits.json"),
        _source("seattle", "https://data.seattle.gov/resource/permits.json"),
    ]

    report = audit_ingestion_hosts(
        entries,
        allowed_hosts="data.austintexas.gov,unused.example.gov",
    )

    assert report.ready is False
    assert report.required_hosts == ["data.austintexas.gov", "data.seattle.gov"]
    assert report.missing_hosts == ["data.seattle.gov"]
    assert report.unused_hosts == ["unused.example.gov"]


def test_shared_policy_distinguishes_coverage_from_exact_parity():
    report = audit_ingestion_hosts(
        [_source("austin", "https://data.austintexas.gov/data")],
        allowed_hosts="data.austintexas.gov,data.seattle.gov",
    )

    assert report.coverage_ready is True
    assert report.ready is False


def test_allowlist_requires_an_exact_reviewed_host():
    report = audit_ingestion_hosts(
        [_source("county", "https://gis.county.example.gov/api")],
        allowed_hosts="example.gov",
    )

    assert report.ready is False
    assert report.missing_hosts == ["gis.county.example.gov"]
    assert report.unused_hosts == ["example.gov"]


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("file:///tmp/permits.csv", "HTTPS"),
        ("https://user:password@example.gov/data", "credentials"),
        ("https://localhost/permits", "localhost"),
        ("https://127.0.0.1/permits", "IP literal"),
        ("https://[::1]/permits", "IP literal"),
        ("https://127.1/permits", "alternate numeric IP"),
        ("https://0x7f.0.0.1/permits", "alternate numeric IP"),
        ("https://data.example.gov:8443/permits", "standard HTTPS port"),
    ],
)
def test_host_policy_rejects_unsafe_source_urls(url, reason):
    report = audit_ingestion_hosts([_source("unsafe", url)], allowed_hosts="example.gov")

    assert report.ready is False
    assert len(report.unsafe_sources) == 1
    assert reason in report.unsafe_sources[0].reason


def test_effective_source_url_matches_connector_override_rules():
    source = _source(
        "override",
        "https://base.example.gov/data",
        connector={"endpoint": "https://api.example.gov/permits"},
    )

    assert effective_source_url(source) == "https://api.example.gov/permits"


def test_host_policy_includes_canary_endpoint_overrides():
    source = _source(
        "probes",
        "https://primary.example.gov/data",
        connector={},
    )
    source.settings["canary_stage_probes"] = [
        {
            "name": "preapproval",
            "connector": {"endpoint": "https://review.example.gov/data"},
        }
    ]
    source.settings["canary_freshness_probe"] = {
        "connector": {"endpoint": "https://localhost/freshness"},
    }

    report = audit_ingestion_hosts(source for source in [source])

    assert {item.purpose for item in report.requirements} == {"primary", "preapproval"}
    assert report.required_hosts == ["primary.example.gov", "review.example.gov"]
    assert report.unsafe_sources[0].reason.startswith("freshness_probe:")


def test_configured_hosts_reject_urls_and_ports():
    with pytest.raises(ValueError, match="Invalid ingestion allowlist host"):
        configured_ingestion_hosts("https://example.gov")
    with pytest.raises(ValueError, match="Invalid ingestion allowlist host"):
        configured_ingestion_hosts("example.gov:443")
    with pytest.raises(ValueError, match="Invalid ingestion allowlist host"):
        configured_ingestion_hosts("127.1")


def test_catalog_host_audit_cli_is_machine_readable(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "load_catalog",
        lambda path=None: [_source("austin", "https://data.austintexas.gov/data")],
    )

    exit_code = cli.main([
        "catalog",
        "host-audit",
        "--allowed-hosts",
        "data.austintexas.gov",
        "--json",
    ])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["ready"] is True


def test_catalog_host_audit_prints_bootstrap_values(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "load_catalog",
        lambda path=None: [_source("austin", "https://data.austintexas.gov/data")],
    )
    monkeypatch.delenv("INGESTION_ALLOWED_HOSTS", raising=False)

    assert cli.main(["catalog", "host-audit", "--print-required-hosts"]) == 0
    assert capsys.readouterr().out.strip() == "data.austintexas.gov"

    assert cli.main([
        "catalog", "host-audit",
        "--allowed-hosts", "data.austintexas.gov",
        "--print-policy-digest",
    ]) == 0
    assert len(capsys.readouterr().out.strip()) == 64


def test_deployed_scheduler_policy_fails_before_execution(monkeypatch):
    monkeypatch.setattr(cli, "ENVIRONMENT", "production")
    monkeypatch.setenv("INGESTION_ALLOWED_HOSTS", "data.austintexas.gov")

    with pytest.raises(ValueError, match="missing hosts: data.seattle.gov"):
        cli._enforce_catalog_host_policy([
            _source("seattle", "https://data.seattle.gov/data")
        ])


def test_deployed_scheduler_rejects_stale_policy_digest(monkeypatch):
    monkeypatch.setattr(cli, "ENVIRONMENT", "production")
    monkeypatch.setenv("INGESTION_ALLOWED_HOSTS", "data.seattle.gov")
    monkeypatch.setenv("INGESTION_HOST_POLICY_DIGEST", "stale-digest")

    with pytest.raises(ValueError, match="digest does not match"):
        cli._enforce_catalog_host_policy([
            _source("seattle", "https://data.seattle.gov/data")
        ])


def test_deployed_scheduler_requires_policy_digest(monkeypatch):
    monkeypatch.setattr(cli, "ENVIRONMENT", "production")
    monkeypatch.setenv("INGESTION_ALLOWED_HOSTS", "data.seattle.gov")
    monkeypatch.delenv("INGESTION_HOST_POLICY_DIGEST", raising=False)

    with pytest.raises(ValueError, match="must be configured"):
        cli._enforce_catalog_host_policy([
            _source("seattle", "https://data.seattle.gov/data")
        ])


def test_plan_policy_is_not_enforced_in_development(monkeypatch):
    monkeypatch.setattr(cli, "ENVIRONMENT", "development")
    monkeypatch.delenv("INGESTION_ALLOWED_HOSTS", raising=False)

    cli._enforce_catalog_host_policy([
        _source("seattle", "https://data.seattle.gov/data")
    ])


def test_host_policy_endpoint_reports_blocked_catalog(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.ingestion.load_catalog",
        lambda: [_source("seattle", "https://data.seattle.gov/data")],
    )
    monkeypatch.setenv("INGESTION_ALLOWED_HOSTS", "data.austintexas.gov")

    response = client.get("/ingestion/host-policy")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["executor_verified"] is False
    assert response.json()["missing_hosts"] == ["data.seattle.gov"]


def test_host_policy_endpoint_requires_named_executor_attestation(client, monkeypatch):
    source = _source("seattle", "https://data.seattle.gov/data")
    monkeypatch.setattr(
        "app.routes.ingestion.load_catalog",
        lambda: [source],
    )
    monkeypatch.setenv("INGESTION_ALLOWED_HOSTS", "data.seattle.gov")
    monkeypatch.setenv("INGESTION_HOST_POLICY_EXECUTOR", "github-production")
    monkeypatch.setenv(
        "INGESTION_HOST_POLICY_DIGEST",
        audit_ingestion_hosts(
            [source], allowed_hosts="data.seattle.gov"
        ).policy_digest,
    )

    response = client.get("/ingestion/host-policy")

    assert response.status_code == 200
    assert response.json()["coverage_ready"] is True
    assert response.json()["ready"] is True
    assert response.json()["executor_name"] == "github-production"
    assert "url" not in response.json()["requirements"][0]


def test_host_policy_redacts_credentials_and_query_tokens():
    report = audit_ingestion_hosts([
        _source(
            "unsafe",
            "https://user:secret@data.example.gov/permits?token=sensitive#fragment",
        )
    ])

    assert report.unsafe_sources[0].url == "https://data.example.gov/permits"
    assert "secret" not in json.dumps(report.unsafe_sources[0].__dict__)
    assert "sensitive" not in json.dumps(report.unsafe_sources[0].__dict__)
