import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from scripts import configure_regional_ingestion as config
from scripts.configure_recurring_columbus import RUNTIME_DATABASE_URL_PARAMETER_ARN


def test_past_daily_start_advances_without_changing_daily_cadence():
    now = datetime(2026, 10, 16, 22, 40, tzinfo=timezone.utc)
    result = config.next_daily_start("2026-10-14T15:13:30-07:00", now=now)
    assert datetime.fromisoformat(result) == datetime(2026, 10, 17, 22, 13, 30, tzinfo=timezone.utc)
    assert config.next_daily_start("2026-10-18T01:00:00Z", now=now) == "2026-10-18T01:00:00Z"


def test_only_verified_sources_receive_tasks_and_schedules(tmp_path, monkeypatch):
    calls = []
    base = {"executionRoleArn": "execution-role", "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"], "cpu": "256", "memory": "512",
        "containerDefinitions": [{
            "entryPoint": ["./docker-entrypoint.sh"],
            "environment": [{"name": "OTHER_SETTING", "value": "preserve"}],
            "secrets": [{"name": "DATABASE_URL", "valueFrom": "admin-reference"},
                        {"name": "SECRET_KEY", "valueFrom": "other-reference"}],
        }]}
    original = deepcopy(base)
    key = "orlando_fl_permit_applications"
    report = tmp_path / "receipt.json"
    report.write_text(json.dumps([{"source_key": key, "status": "verified"},
                                  {"source_key": "unreviewed", "status": "blocked"}]))
    monkeypatch.setattr(config.time, "sleep", lambda seconds: None)

    def aws(*args):
        calls.append(args)
        if args[:2] == ("sts", "get-caller-identity"):
            return {"Account": config.ACCOUNT}
        if args[:2] == ("ecs", "describe-task-definition"):
            return {"taskDefinition": base}
        if args[:2] == ("ecs", "register-task-definition"):
            return {"taskDefinition": {"taskDefinitionArn": "pinned-task:1"}}
        if args[:2] == ("scheduler", "get-schedule"):
            return {"StartDate": "2026-10-17T01:00:00Z"}
        return {}

    monkeypatch.setattr(config, "aws", aws)
    # Pin "now" so an existing future StartDate is preserved rather than advanced by
    # the ambient wall clock; the assertion below checks that un-advanced value.
    _next_daily_start = config.next_daily_start
    monkeypatch.setattr(
        config, "next_daily_start",
        lambda value, now=datetime(2026, 10, 16, tzinfo=timezone.utc): _next_daily_start(value, now=now),
    )
    monkeypatch.setattr(config, "exists_or_create", lambda *args, **kwargs: {"Role": {"Arn": "scheduler-role"}})
    image = f"{config.ACCOUNT}.dkr.ecr.{config.REGION}.amazonaws.com/dealsignal-api@sha256:" + "a" * 64
    config.configure("customer", image, report)
    task = next(json.loads(row[-1]) for row in calls if row[:2] == ("ecs", "register-task-definition"))
    container = task["containerDefinitions"][0]
    assert container["command"][-1] == key
    assert container["environment"] == [
        {"name": "OTHER_SETTING", "value": "preserve"},
        {"name": "INGESTION_ALLOWED_HOSTS", "value": "data.cityoforlando.net"},
    ]
    assert container["secrets"] == [
        {"name": "DATABASE_URL", "valueFrom": RUNTIME_DATABASE_URL_PARAMETER_ARN},
        {"name": "SECRET_KEY", "valueFrom": "other-reference"},
    ]
    assert container["image"] == image
    assert container["entryPoint"] == base["containerDefinitions"][0]["entryPoint"]
    for field in ("executionRoleArn", "networkMode", "requiresCompatibilities", "cpu", "memory"):
        assert task[field] == base[field]
    assert base == original
    schedule = next(json.loads(row[-1]) for row in calls if row[:2] == ("scheduler", "update-schedule"))
    assert schedule["StartDate"] == "2026-10-17T01:00:00Z"
    assert schedule["Target"]["EcsParameters"]["TaskDefinitionArn"] == "pinned-task:1"
    assert schedule["ScheduleExpression"] == "rate(1 day)"
    assert len([row for row in calls if row[:2] == ("ecs", "register-task-definition")]) == 1


def test_rerun_preserves_previously_scheduled_task_arns(tmp_path, monkeypatch):
    key = "orlando_fl_permit_applications"
    report = tmp_path / "receipt.json"
    report.write_text(json.dumps([{"source_key": key, "status": "verified"}]))
    monkeypatch.setattr(config.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(config, "exists_or_create", lambda *args, **kwargs: {"Role": {"Arn": "scheduler-role"}})
    monkeypatch.setattr(config, "next_daily_start", lambda value, now=None: value)
    calls = []

    def aws(*args):
        calls.append(args)
        if args[:2] == ("sts", "get-caller-identity"):
            return {"Account": config.ACCOUNT}
        if args[:2] == ("ecs", "describe-task-definition"):
            return {"taskDefinition": {"executionRoleArn": "execution-role", "networkMode": "awsvpc",
                "requiresCompatibilities": ["FARGATE"], "cpu": "256", "memory": "512",
                "containerDefinitions": [{"secrets": [{"name": "DATABASE_URL", "valueFrom": "admin-reference"}]}]}}
        if args[:2] == ("ecs", "register-task-definition"):
            return {"taskDefinition": {"taskDefinitionArn": "pinned-task:2"}}
        if args[:2] == ("iam", "get-role-policy"):
            # A prior run already granted RunTask for another source's schedule.
            return {"PolicyDocument": {"Statement": [
                {"Effect": "Allow", "Action": "ecs:RunTask", "Resource": ["older-task:1"]},
                {"Effect": "Allow", "Action": "iam:PassRole", "Resource": "execution-role"}]}}
        if args[:2] == ("scheduler", "get-schedule"):
            return {"StartDate": "2026-10-18T01:00:00Z"}
        return {}

    monkeypatch.setattr(config, "aws", aws)
    image = f"{config.ACCOUNT}.dkr.ecr.{config.REGION}.amazonaws.com/dealsignal-api@sha256:" + "a" * 64
    config.configure("customer", image, report)

    policy = next(
        json.loads(row[row.index("--policy-document") + 1])
        for row in calls if row[:2] == ("iam", "put-role-policy")
    )
    run_task = next(s for s in policy["Statement"] if s["Action"] == "ecs:RunTask")
    # The omitted source's existing task ARN is preserved alongside the new one.
    assert "older-task:1" in run_task["Resource"]
    assert "pinned-task:2" in run_task["Resource"]


@pytest.mark.parametrize("container", [
    {},
    {"secrets": [{"name": "SECRET_KEY", "valueFrom": "other-reference"}]},
    {"secrets": [{"name": "DATABASE_URL", "valueFrom": "first-reference"},
                 {"name": "DATABASE_URL", "valueFrom": "second-reference"}]},
    {"secrets": [{"name": "DATABASE_URL", "valueFrom": "admin-reference"}],
     "environment": [{"name": "DATABASE_URL", "value": "plaintext-must-not-be-used"}]},
])
def test_invalid_database_reference_stops_before_any_cloud_mutation(container, tmp_path, monkeypatch):
    report = tmp_path / "receipt.json"
    report.write_text(json.dumps([{"source_key": "orlando_fl_permit_applications", "status": "verified"}]))
    calls = []
    original = deepcopy(container)

    def aws(*args):
        calls.append(args[:2])
        if args[:2] == ("sts", "get-caller-identity"):
            return {"Account": config.ACCOUNT}
        if args[:2] == ("ecs", "describe-task-definition"):
            return {"taskDefinition": {"containerDefinitions": [container]}}
        pytest.fail("Cloud mutation must not follow an invalid DATABASE_URL contract")

    monkeypatch.setattr(config, "aws", aws)
    monkeypatch.setattr(config, "exists_or_create",
                        lambda *args, **kwargs: pytest.fail("No resources may be created"))
    image = f"{config.ACCOUNT}.dkr.ecr.{config.REGION}.amazonaws.com/dealsignal-api@sha256:" + "a" * 64
    with pytest.raises(ValueError, match="DATABASE_URL"):
        config.configure("customer", image, report)
    assert calls == [("sts", "get-caller-identity"), ("ecs", "describe-task-definition")]
    assert container == original


def test_empty_or_unreviewed_receipt_is_rejected_before_aws(tmp_path, monkeypatch):
    report = tmp_path / "receipt.json"
    report.write_text(json.dumps([{"source_key": "unreviewed", "status": "verified"}]))
    monkeypatch.setattr(config, "aws", lambda *args: pytest.fail("No cloud requests expected"))
    image = f"{config.ACCOUNT}.dkr.ecr.{config.REGION}.amazonaws.com/dealsignal-api@sha256:" + "a" * 64
    with pytest.raises(ValueError, match="unknown"):
        config.configure("customer", image, report)
