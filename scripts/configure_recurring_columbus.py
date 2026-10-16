"""Provision two explicitly authorized, versioned AWS scheduled ingestion tasks."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.demo_access import DEMO_ORG_ID

REGION = "us-east-1"
ACCOUNT = "159667575905"
GROUP = "buildsignals-ingestion"
CLUSTER = f"arn:aws:ecs:{REGION}:{ACCOUNT}:cluster/dealsignal-cicd"
ROLE = "buildsignals-ingestion-scheduler"
NETWORK = {"awsvpcConfiguration": {
    "Subnets": ["subnet-0c8429050054303f3", "subnet-0fa5022e747596511"],
    "SecurityGroups": ["sg-0730b1695dc68bc4e"], "AssignPublicIp": "ENABLED",
}}


def aws(*args):
    result = subprocess.run(["aws", "--region", REGION, *args, "--output", "json"],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def exists_or_create(service, describe, create, **kwargs):
    try:
        return aws(service, describe, *kwargs["describe_args"])
    except subprocess.CalledProcessError as exc:
        if not any(code in exc.stderr for code in ("ResourceNotFoundException", "NoSuchEntity")):
            raise
        return aws(service, create, *kwargs["create_args"])


def configure(organization_id: str, image: str):
    if not organization_id or organization_id == DEMO_ORG_ID or "@sha256:" not in image:
        raise ValueError("Explicit production tenant and immutable image digest required")
    base = aws("ecs", "describe-task-definition", "--task-definition", "dealsignal-migrate:2")["taskDefinition"]
    code = Path(__file__).with_name("recurring_columbus.py").read_text()
    exists_or_create("scheduler", "get-schedule-group", "create-schedule-group",
                     describe_args=["--name", GROUP], create_args=["--name", GROUP])
    try:
        aws("logs", "create-log-group", "--log-group-name", "/ecs/buildsignals-ingestion")
    except subprocess.CalledProcessError as exc:
        if "ResourceAlreadyExistsException" not in exc.stderr:
            raise
    aws("logs", "put-retention-policy", "--log-group-name", "/ecs/buildsignals-ingestion", "--retention-in-days", "30")
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "scheduler.amazonaws.com"},
        "Action": "sts:AssumeRole", "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT},
        "ArnEquals": {"aws:SourceArn": f"arn:aws:scheduler:{REGION}:{ACCOUNT}:schedule-group/{GROUP}"}}}]}
    role = exists_or_create("iam", "get-role", "create-role", describe_args=["--role-name", ROLE],
        create_args=["--role-name", ROLE, "--assume-role-policy-document", json.dumps(trust)])["Role"]["Arn"]
    # Preserve no broader trust if a previous version exists.
    aws("iam", "update-assume-role-policy", "--role-name", ROLE, "--policy-document", json.dumps(trust))
    definitions = {}
    for mode, org in [("production", organization_id), ("demo", DEMO_ORG_ID)]:
        container = dict(base["containerDefinitions"][0])
        container.update(name="worker", image=image, command=["python", "-c", code, "--organization-id", org] + (["--demo"] if mode == "demo" else []))
        container["environment"] = [row for row in container.get("environment", []) if row["name"] != "INGESTION_ALLOWED_HOSTS"] + [{"name": "INGESTION_ALLOWED_HOSTS", "value": "maps2.columbus.gov"}]
        container["logConfiguration"] = {"logDriver": "awslogs", "options": {
            "awslogs-group": "/ecs/buildsignals-ingestion", "awslogs-region": REGION, "awslogs-stream-prefix": mode}}
        spec = {key: base[key] for key in ["executionRoleArn", "networkMode", "requiresCompatibilities", "cpu", "memory"]}
        spec.update(family=f"buildsignals-columbus-{mode}", containerDefinitions=[container])
        definitions[mode] = aws("ecs", "register-task-definition", "--cli-input-json", json.dumps(spec))["taskDefinition"]["taskDefinitionArn"]
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "ecs:RunTask", "Resource": list(definitions.values()), "Condition": {"ArnEquals": {"ecs:cluster": CLUSTER}}},
        {"Effect": "Allow", "Action": "iam:PassRole", "Resource": base["executionRoleArn"], "Condition": {"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}},
    ]}
    aws("iam", "put-role-policy", "--role-name", ROLE, "--policy-name", "RunReviewedColumbusTasks", "--policy-document", json.dumps(policy))
    for index, (mode, task) in enumerate(definitions.items()):
        # Start shortly for an actual scheduled receipt, then repeat daily.
        first = datetime.now(timezone.utc) + timedelta(minutes=3 + index * 2)
        name = f"columbus-{mode}-daily"
        target = {"Arn": CLUSTER, "RoleArn": role, "EcsParameters": {"TaskDefinitionArn": task,
            "LaunchType": "FARGATE", "TaskCount": 1, "NetworkConfiguration": NETWORK},
            "RetryPolicy": {"MaximumEventAgeInSeconds": 900, "MaximumRetryAttempts": 2}}
        spec = {"Name": name, "GroupName": GROUP, "ScheduleExpression": "rate(1 day)",
            "StartDate": first.isoformat(), "ScheduleExpressionTimezone": "UTC",
            "FlexibleTimeWindow": {"Mode": "OFF"}, "State": "ENABLED", "Target": target}
        try:
            aws("scheduler", "get-schedule", "--name", name, "--group-name", GROUP)
            action = "update-schedule"
        except subprocess.CalledProcessError as exc:
            if "ResourceNotFoundException" not in exc.stderr:
                raise
            action = "create-schedule"
        aws("scheduler", action, "--cli-input-json", json.dumps(spec))
        print(json.dumps({"schedule": name, "task_definition": task, "first_at_utc": first.isoformat()}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--confirm-production", action="store_true", required=True)
    args = parser.parse_args()
    configure(args.organization_id, args.image)
