import json

import pytest

from scripts import configure_recurring_columbus as provision


def test_registration_pins_image_and_scheduler_permissions(monkeypatch):
    calls = []

    def aws(*args):
        calls.append(args)
        if args[:2] == ("ecs", "describe-task-definition"):
            return {"taskDefinition": {
                "executionRoleArn": "arn:aws:iam::159667575905:role/execution",
                "networkMode": "awsvpc", "requiresCompatibilities": ["FARGATE"],
                "cpu": "256", "memory": "512",
                "containerDefinitions": [{"environment": [], "secrets": [{"name": "DATABASE_URL", "valueFrom": "managed-secret-reference"}]}],
            }}
        if args[:2] == ("iam", "get-role"):
            return {"Role": {"Arn": "arn:aws:iam::159667575905:role/scheduler"}}
        if args[:2] == ("ecs", "register-task-definition"):
            spec = json.loads(args[-1])
            return {"taskDefinition": {"taskDefinitionArn": "arn:aws:ecs:us-east-1:159667575905:task-definition/" + spec["family"] + ":1"}}
        return {}

    monkeypatch.setattr(provision, "aws", aws)
    image = "repository@sha256:" + "a" * 64
    provision.configure("customer", image)
    tasks = [json.loads(args[-1]) for args in calls if args[:2] == ("ecs", "register-task-definition")]
    assert len(tasks) == 2
    for task in tasks:
        container = task["containerDefinitions"][0]
        assert container["image"] == image
        assert container["secrets"][0]["valueFrom"] == "managed-secret-reference"
        assert container["environment"] == [{"name": "INGESTION_ALLOWED_HOSTS", "value": "maps2.columbus.gov"}]
    policy = next(json.loads(args[-1]) for args in calls if args[:2] == ("iam", "put-role-policy"))
    assert len(policy["Statement"][0]["Resource"]) == 2
    assert policy["Statement"][0]["Condition"]["ArnEquals"]["ecs:cluster"] == provision.CLUSTER
    assert policy["Statement"][1]["Action"] == "iam:PassRole"
    schedules = [json.loads(args[-1]) for args in calls if args[:2] == ("scheduler", "update-schedule")]
    assert len(schedules) == 2
    assert all(row["ScheduleExpression"] == "rate(1 day)" for row in schedules)
    assert all(row["Target"]["EcsParameters"]["TaskCount"] == 1 for row in schedules)


@pytest.mark.parametrize("org,image", [("", "repo@sha256:abc"), ("customer", "repo:latest"), (provision.DEMO_ORG_ID, "repo@sha256:abc")])
def test_provisioning_rejects_unsafe_inputs_before_cloud_calls(org, image, monkeypatch):
    monkeypatch.setattr(provision, "aws", lambda *args: pytest.fail("No cloud requests permitted"))
    with pytest.raises(ValueError):
        provision.configure(org, image)
