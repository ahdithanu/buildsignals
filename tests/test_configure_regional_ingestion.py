import json
from datetime import datetime, timezone

import pytest

from scripts import configure_regional_ingestion as config


def test_past_daily_start_advances_without_changing_daily_cadence():
    now = datetime(2026, 10, 16, 22, 40, tzinfo=timezone.utc)
    result = config.next_daily_start("2026-10-14T15:13:30-07:00", now=now)
    assert datetime.fromisoformat(result) == datetime(2026, 10, 17, 22, 13, 30, tzinfo=timezone.utc)
    assert config.next_daily_start("2026-10-18T01:00:00Z", now=now) == "2026-10-18T01:00:00Z"


def test_only_verified_sources_receive_tasks_and_schedules(tmp_path, monkeypatch):
    calls = []
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
            return {"taskDefinition": {"executionRoleArn": "execution-role", "networkMode": "awsvpc",
                "requiresCompatibilities": ["FARGATE"], "cpu": "256", "memory": "512",
                "containerDefinitions": [{"secrets": [{"name": "DATABASE_URL", "valueFrom": "reference-only"}]}]}}
        if args[:2] == ("ecs", "register-task-definition"):
            return {"taskDefinition": {"taskDefinitionArn": "pinned-task:1"}}
        if args[:2] == ("scheduler", "get-schedule"):
            return {"StartDate": "2026-10-17T01:00:00Z"}
        return {}

    monkeypatch.setattr(config, "aws", aws)
    monkeypatch.setattr(config, "exists_or_create", lambda *args, **kwargs: {"Role": {"Arn": "scheduler-role"}})
    image = f"{config.ACCOUNT}.dkr.ecr.{config.REGION}.amazonaws.com/dealsignal-api@sha256:" + "a" * 64
    config.configure("customer", image, report)
    task = next(json.loads(row[-1]) for row in calls if row[:2] == ("ecs", "register-task-definition"))
    container = task["containerDefinitions"][0]
    assert container["command"][-1] == key
    assert container["environment"] == [{"name": "INGESTION_ALLOWED_HOSTS", "value": "data.cityoforlando.net"}]
    assert container["secrets"][0]["valueFrom"] == "reference-only"
    schedule = next(json.loads(row[-1]) for row in calls if row[:2] == ("scheduler", "update-schedule"))
    assert schedule["StartDate"] == "2026-10-17T01:00:00Z"
    assert schedule["Target"]["EcsParameters"]["TaskDefinitionArn"] == "pinned-task:1"
    assert schedule["ScheduleExpression"] == "rate(1 day)"
    assert len([row for row in calls if row[:2] == ("ecs", "register-task-definition")]) == 1


def test_empty_or_unreviewed_receipt_is_rejected_before_aws(tmp_path, monkeypatch):
    report = tmp_path / "receipt.json"
    report.write_text(json.dumps([{"source_key": "unreviewed", "status": "verified"}]))
    monkeypatch.setattr(config, "aws", lambda *args: pytest.fail("No cloud requests expected"))
    image = f"{config.ACCOUNT}.dkr.ecr.{config.REGION}.amazonaws.com/dealsignal-api@sha256:" + "a" * 64
    with pytest.raises(ValueError, match="unknown"):
        config.configure("customer", image, report)
