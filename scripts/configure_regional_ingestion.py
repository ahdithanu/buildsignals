"""Install daily jobs only for explicitly verified reviewed regional sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.services.demo_access import DEMO_ORG_ID
from scripts.configure_recurring_columbus import (
    ACCOUNT,
    CLUSTER,
    GROUP,
    NETWORK,
    REGION,
    aws,
    exists_or_create,
)
from scripts.recurring_regions import SOURCES, regional_entry

ROLE = "buildsignals-regional-scheduler"


def job_name(key):
    return "region-" + key[:43] + "-" + hashlib.sha256(key.encode()).hexdigest()[:8]


def configure(org, image, report_path):
    if not org or org == DEMO_ORG_ID or not re.fullmatch(rf"{ACCOUNT}\.dkr\.ecr\.{REGION}\.amazonaws\.com/dealsignal-api@sha256:[a-f0-9]{{64}}", image):
        raise ValueError("Explicit production tenant and reviewed immutable image required")
    if time.time() - report_path.stat().st_mtime > 3600:
        raise ValueError("Reverify sources; receipt must be less than one hour old")
    rows = json.loads(report_path.read_text())
    keys = sorted({row["source_key"] for row in rows if row["status"] == "verified"})
    if not keys or set(keys) - set(SOURCES):
        raise ValueError("Report includes no approved sources or unknown sources")
    if aws("sts", "get-caller-identity")["Account"] != ACCOUNT:
        raise ValueError("Unexpected AWS account")
    base = aws("ecs", "describe-task-definition", "--task-definition", "dealsignal-migrate:2")["taskDefinition"]
    code = Path(__file__).with_name("recurring_regions.py").read_text()
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "scheduler.amazonaws.com"},
        "Action": "sts:AssumeRole", "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT},
        "ArnEquals": {"aws:SourceArn": f"arn:aws:scheduler:{REGION}:{ACCOUNT}:schedule-group/{GROUP}"}}}]}
    role = exists_or_create("iam", "get-role", "create-role", describe_args=["--role-name", ROLE],
        create_args=["--role-name", ROLE, "--assume-role-policy-document", json.dumps(trust)])["Role"]["Arn"]
    aws("iam", "update-assume-role-policy", "--role-name", ROLE, "--policy-document", json.dumps(trust))
    tasks = {}
    for key in keys:
        entry = regional_entry(key)
        container = dict(base["containerDefinitions"][0])
        container.update(name="worker", image=image, command=["python", "-c", code, "--organization-id", org, "--source-key", key])
        host = urlparse(entry.base_url).hostname
        container["environment"] = [row for row in container.get("environment", []) if row["name"] != "INGESTION_ALLOWED_HOSTS"] + [{"name": "INGESTION_ALLOWED_HOSTS", "value": host}]
        container["logConfiguration"] = {"logDriver": "awslogs", "options": {
            "awslogs-group": "/ecs/buildsignals-ingestion", "awslogs-region": REGION, "awslogs-stream-prefix": job_name(key)}}
        spec = {field: base[field] for field in ["executionRoleArn", "networkMode", "requiresCompatibilities", "cpu", "memory"]}
        spec.update(family="buildsignals-" + job_name(key), containerDefinitions=[container])
        tasks[key] = aws("ecs", "register-task-definition", "--cli-input-json", json.dumps(spec))["taskDefinition"]["taskDefinitionArn"]
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "ecs:RunTask", "Resource": list(tasks.values()), "Condition": {"ArnEquals": {"ecs:cluster": CLUSTER}}},
        {"Effect": "Allow", "Action": "iam:PassRole", "Resource": base["executionRoleArn"], "Condition": {"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}},
    ]}
    aws("iam", "put-role-policy", "--role-name", ROLE, "--policy-name", "RunVerifiedRegionalTasks", "--policy-document", json.dumps(policy))
    # Allow newly created IAM role/policy to propagate before scheduler validation.
    time.sleep(15)
    first = datetime.now(timezone.utc) + timedelta(minutes=3)
    for index, (key, task) in enumerate(tasks.items()):
        name = job_name(key)
        target = {"Arn": CLUSTER, "RoleArn": role, "EcsParameters": {"TaskDefinitionArn": task,
            "LaunchType": "FARGATE", "TaskCount": 1, "NetworkConfiguration": NETWORK},
            "RetryPolicy": {"MaximumEventAgeInSeconds": 900, "MaximumRetryAttempts": 2}}
        try:
            existing = aws("scheduler", "get-schedule", "--name", name, "--group-name", GROUP)
            start = existing["StartDate"]
            action = "update-schedule"
        except subprocess.CalledProcessError as exc:
            if "ResourceNotFoundException" not in exc.stderr:
                raise
            start = (first + timedelta(seconds=index * 10)).isoformat()
            action = "create-schedule"
        spec = {"Name": name, "GroupName": GROUP, "ScheduleExpression": "rate(1 day)",
                "StartDate": start, "FlexibleTimeWindow": {"Mode": "OFF"}, "State": "ENABLED", "Target": target}
        aws("scheduler", action, "--cli-input-json", json.dumps(spec))
        print(json.dumps({"source_key": key, "schedule": name, "task_definition": task, "start": start}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--verified-report", type=Path, required=True)
    parser.add_argument("--confirm-production", action="store_true", required=True)
    args = parser.parse_args()
    configure(args.organization_id, args.image, args.verified_report)
