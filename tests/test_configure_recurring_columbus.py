import json
from copy import deepcopy

import pytest

from scripts import configure_recurring_columbus as provision


def test_registration_pins_image_and_scheduler_permissions(monkeypatch):
    calls = []
    base = {
        "executionRoleArn": "arn:aws:iam::159667575905:role/execution",
        "networkMode": "awsvpc", "requiresCompatibilities": ["FARGATE"],
        "cpu": "256", "memory": "512",
        "containerDefinitions": [{
            "environment": [{"name": "OTHER_SETTING", "value": "preserve"}],
            "entryPoint": ["./docker-entrypoint.sh"],
            "secrets": [{"name": "DATABASE_URL", "valueFrom": "managed-admin-reference"},
                        {"name": "SECRET_KEY", "valueFrom": "other-secret-reference"}],
        }],
    }
    original = deepcopy(base)

    def aws(*args):
        calls.append(args)
        if args[:2] == ("sts", "get-caller-identity"):
            return {"Account": provision.ACCOUNT}
        if args[:2] == ("ecs", "describe-task-definition"):
            return {"taskDefinition": base}
        if args[:2] == ("iam", "get-role"):
            return {"Role": {"Arn": "arn:aws:iam::159667575905:role/scheduler"}}
        if args[:2] == ("ecs", "register-task-definition"):
            spec = json.loads(args[-1])
            return {"taskDefinition": {"taskDefinitionArn": "arn:aws:ecs:us-east-1:159667575905:task-definition/" + spec["family"] + ":1"}}
        return {}

    monkeypatch.setattr(provision, "aws", aws)
    image = f"{provision.ACCOUNT}.dkr.ecr.{provision.REGION}.amazonaws.com/dealsignal-api@sha256:" + "a" * 64
    provision.configure("customer", image)
    tasks = [json.loads(args[-1]) for args in calls if args[:2] == ("ecs", "register-task-definition")]
    assert len(tasks) == 2
    for task in tasks:
        container = task["containerDefinitions"][0]
        assert container["image"] == image
        assert container["secrets"] == [
            {"name": "DATABASE_URL", "valueFrom": provision.RUNTIME_DATABASE_URL_PARAMETER_ARN},
            {"name": "SECRET_KEY", "valueFrom": "other-secret-reference"},
        ]
        assert container["environment"] == [
            {"name": "OTHER_SETTING", "value": "preserve"},
            {"name": "INGESTION_ALLOWED_HOSTS", "value": "maps2.columbus.gov"},
        ]
        assert container["entryPoint"] == base["containerDefinitions"][0]["entryPoint"]
        for field in ("executionRoleArn", "networkMode", "requiresCompatibilities", "cpu", "memory"):
            assert task[field] == base[field]
    assert base == original
    policy = next(json.loads(args[-1]) for args in calls if args[:2] == ("iam", "put-role-policy"))
    assert len(policy["Statement"][0]["Resource"]) == 2
    assert policy["Statement"][0]["Condition"]["ArnEquals"]["ecs:cluster"] == provision.CLUSTER
    assert policy["Statement"][1]["Action"] == "iam:PassRole"
    schedules = [json.loads(args[-1]) for args in calls if args[:2] == ("scheduler", "update-schedule")]
    assert len(schedules) == 2
    assert all(row["ScheduleExpression"] == "rate(1 day)" for row in schedules)
    assert all(row["Target"]["EcsParameters"]["TaskCount"] == 1 for row in schedules)


def test_runtime_container_changes_only_database_reference_and_is_deep_copied():
    base = {
        "name": "migration", "image": "existing-image", "command": ["migrate"],
        "environment": [{"name": "OTHER", "value": "preserved"}],
        "secrets": [
            {"name": "SECRET_KEY", "valueFrom": "unchanged-reference"},
            {"name": "DATABASE_URL", "valueFrom": "admin-reference"},
        ],
        "logConfiguration": {"options": {"awslogs-group": "existing-group"}},
    }
    original = deepcopy(base)
    result = provision.runtime_container(base)
    expected = deepcopy(base)
    expected["secrets"][1]["valueFrom"] = (
        "arn:aws:ssm:us-east-1:159667575905:parameter/buildsignals/production/runtime-database-url-v1"
    )
    assert result == expected
    assert base == original
    result["environment"][0]["value"] = "changed"
    result["secrets"][0]["valueFrom"] = "changed"
    result["logConfiguration"]["options"]["awslogs-group"] = "changed"
    result["command"].append("changed")
    assert base == original


@pytest.mark.parametrize("container", [
    {},
    {"secrets": [{"name": "SECRET_KEY", "valueFrom": "other-reference"}]},
    {"secrets": [{"name": "DATABASE_URL", "valueFrom": "first-reference"},
                 {"name": "DATABASE_URL", "valueFrom": "second-reference"}]},
    {"secrets": [{"name": "DATABASE_URL", "valueFrom": "admin-reference"}],
     "environment": [{"name": "DATABASE_URL", "value": "plaintext-must-not-be-used"}]},
])
def test_invalid_database_reference_stops_before_any_cloud_mutation(container, monkeypatch):
    calls = []
    original = deepcopy(container)

    def aws(*args):
        calls.append(args[:2])
        if args[:2] == ("sts", "get-caller-identity"):
            return {"Account": provision.ACCOUNT}
        if args[:2] == ("ecs", "describe-task-definition"):
            return {"taskDefinition": {"containerDefinitions": [container]}}
        pytest.fail("Cloud mutation must not follow an invalid DATABASE_URL contract")

    monkeypatch.setattr(provision, "aws", aws)
    monkeypatch.setattr(provision, "exists_or_create",
                        lambda *args, **kwargs: pytest.fail("No resources may be created"))
    image = f"{provision.ACCOUNT}.dkr.ecr.{provision.REGION}.amazonaws.com/dealsignal-api@sha256:" + "a" * 64
    with pytest.raises(ValueError, match="DATABASE_URL"):
        provision.configure("customer", image)
    assert calls == [("sts", "get-caller-identity"), ("ecs", "describe-task-definition")]
    assert container == original


@pytest.mark.parametrize("org,image", [("", "repo@sha256:abc"), ("customer", "repo:latest"), ("customer", "untrusted@sha256:" + "a" * 64), (provision.DEMO_ORG_ID, "repo@sha256:abc")])
def test_provisioning_rejects_unsafe_inputs_before_cloud_calls(org, image, monkeypatch):
    monkeypatch.setattr(provision, "aws", lambda *args: pytest.fail("No cloud requests permitted"))
    with pytest.raises(ValueError):
        provision.configure(org, image)


def test_wrong_aws_account_stops_before_resources_are_changed(monkeypatch):
    def aws(*args):
        assert args == ("sts", "get-caller-identity")
        return {"Account": "different"}
    monkeypatch.setattr(provision, "aws", aws)
    image = f"{provision.ACCOUNT}.dkr.ecr.{provision.REGION}.amazonaws.com/dealsignal-api@sha256:" + "a" * 64
    with pytest.raises(ValueError, match="unexpected AWS account"):
        provision.configure("customer", image)
