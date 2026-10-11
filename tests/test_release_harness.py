from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import release_harness as harness

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_harness.py"


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state",
            str(tmp_path / "state.json"),
            "--lock",
            str(tmp_path / "harness.lock"),
            *args,
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        timeout=10,
    )


def _state(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "state.json").read_text())


def _completed(stdout: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(stdout), stderr="")


def _runner_for(
    *,
    rollup: list[dict] | None = None,
    deployments: list[dict] | None = None,
    statuses: list[dict] | None = None,
    sha: str = "sha-1",
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(command, **_kwargs):
        joined = " ".join(command)
        if command[:3] == ["gh", "pr", "view"]:
            return _completed(
                {
                    "number": 127,
                    "url": "https://github.example/pr/127",
                    "state": "OPEN",
                    "isDraft": False,
                    "headRefOid": sha,
                    "mergeCommit": None,
                    "mergeStateStatus": "CLEAN",
                    "statusCheckRollup": rollup if rollup is not None else [],
                }
            )
        if "/branches/main" in joined:
            return _completed({"commit": {"sha": sha}})
        if "/check-runs" in joined:
            return _completed({"check_runs": rollup if rollup is not None else []})
        if "/status" in joined and "/statuses" not in joined:
            return _completed({"statuses": []})
        if "/statuses" in joined:
            return _completed(statuses if statuses is not None else [])
        if "/deployments" in joined:
            return _completed(deployments if deployments is not None else [])
        raise AssertionError(f"unexpected command: {command}")

    return run


def test_start_persists_exact_sha_without_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "current_git_ref", lambda: ("feature/release", "abc123def456"))
    state = harness.ReleaseState(tmp_path / "state.json")
    state.begin(pr="127", dry_run=True)
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["head_sha"] == "abc123def456"
    assert data["pr"] == "127"
    assert data["mode"] == "dry-run"
    assert "token" not in json.dumps(data).lower()


def test_resume_waits_on_duplicate_pending_event_without_new_action(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "current_git_ref", lambda: ("feature/release", "sha-1"))
    state = harness.ReleaseState(tmp_path / "state.json")
    state.begin(pr="128", dry_run=True)
    observed = {"head_sha": "sha-1", "checks": "pending", "run_id": "run-1"}
    assert harness.reconcile(state, observed) == "waiting"
    first = json.loads((tmp_path / "state.json").read_text())
    assert harness.reconcile(harness.ReleaseState(tmp_path / "state.json"), observed) == "waiting"
    second = json.loads((tmp_path / "state.json").read_text())
    assert second["phase"] == "waiting"
    assert second["external"]["run_id"] == "run-1"
    assert second["next_action"] == first["next_action"]


def test_resume_without_observed_state_waits_instead_of_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "current_git_ref", lambda: ("feature/release", "sha-1"))
    state = harness.ReleaseState(tmp_path / "state.json")
    state.begin(pr="128", dry_run=True)
    assert harness.reconcile(state, {}) == "waiting"
    assert json.loads((tmp_path / "state.json").read_text())["waiting_reason"] == "no observed state"


def test_resume_blocks_superseded_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "current_git_ref", lambda: ("feature/release", "expected"))
    state = harness.ReleaseState(tmp_path / "state.json")
    state.begin(pr="129", dry_run=True)
    assert harness.reconcile(state, {"head_sha": "newer"}) == "failure"
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["failure_reason"] == "superseded commit observed"
    assert data["events"][-1]["detail"]["expected_sha"] == "expected"


def test_resume_blocks_deployment_target_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "current_git_ref", lambda: ("feature/release", "sha-1"))
    state = harness.ReleaseState(tmp_path / "state.json")
    state.begin(pr="130", dry_run=True)
    state.mark_waiting("deployment pending", deployment_id="dep-1", deployment_target="production")
    assert harness.reconcile(
        harness.ReleaseState(tmp_path / "state.json"),
        {"head_sha": "sha-1", "deployment_id": "dep-1", "deployment_target": "preview"},
    ) == "failure"
    assert json.loads((tmp_path / "state.json").read_text())["failure_reason"] == "deployment target mismatch"


def test_resume_blocks_deployment_identity_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "current_git_ref", lambda: ("feature/release", "sha-1"))
    state = harness.ReleaseState(tmp_path / "state.json")
    state.begin(pr="131", dry_run=True)
    state.mark_waiting("deployment pending", deployment_id="dep-1", deployment_target="production")
    assert harness.reconcile(
        harness.ReleaseState(tmp_path / "state.json"),
        {"head_sha": "sha-1", "deployment_id": "dep-2", "deployment_target": "production"},
    ) == "failure"
    assert json.loads((tmp_path / "state.json").read_text())["failure_reason"] == "deployment identity mismatch"


def test_github_adapter_maps_completed_checks_and_deployment_identity():
    observed = harness.collect_github_observed(
        pr="127",
        repository="ahdithanu/buildsignals",
        runner=_runner_for(
            rollup=[
                {
                    "name": "test",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "workflowRun": {"databaseId": 1001},
                },
                {"name": "frontend", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "pre-commit", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "gitleaks", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ],
            deployments=[
                {
                    "id": 2002,
                    "environment": "production",
                    "statuses_url": "https://api.github.com/repos/ahdithanu/buildsignals/deployments/2002/statuses",
                }
            ],
            statuses=[{"id": 3003, "state": "success", "target_url": "https://preview.example"}],
        ),
    )
    assert observed["head_sha"] == "sha-1"
    assert observed["checks"] == "passed"
    assert observed["run_id"] == "1001"
    assert observed["deployment_id"] == "2002"
    assert observed["deployment_target"] == "production"
    assert observed["deployment_status"] == "ready"
    assert observed["deployment_target_url"] == "https://preview.example"


@pytest.mark.parametrize(
    ("rollup", "expected"),
    [
        ([{"status": "IN_PROGRESS", "conclusion": None}], "pending"),
        ([{"name": "test", "status": "COMPLETED", "conclusion": "FAILURE"}], "failed"),
        ([{"name": "test", "status": "COMPLETED", "conclusion": "CANCELLED"}], "failed"),
        ([{"name": "test", "status": "COMPLETED", "conclusion": "SKIPPED"}], "failed"),
    ],
)
def test_github_adapter_check_state_mapping(rollup, expected):
    observed = harness.collect_github_observed(
        pr="127",
        repository="ahdithanu/buildsignals",
        runner=_runner_for(rollup=rollup),
    )
    assert observed["checks"] == expected


def test_github_adapter_accepts_success_status_context():
    observed = harness.collect_github_observed(
        pr="127",
        repository="ahdithanu/buildsignals",
        runner=_runner_for(
            rollup=[
                {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "frontend", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "pre-commit", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "gitleaks", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"__typename": "StatusContext", "context": "Vercel", "state": "SUCCESS", "targetUrl": "https://vercel.example/deploy"},
            ]
        ),
    )
    assert observed["checks"] == "passed"
    assert observed["run_id"] == "https://vercel.example/deploy"


def test_partial_rollup_does_not_pass_required_checks():
    observed = harness.collect_github_observed(
        pr="127",
        repository="ahdithanu/buildsignals",
        runner=_runner_for(
            rollup=[
                {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"__typename": "StatusContext", "context": "Vercel", "state": "SUCCESS"},
            ]
        ),
    )
    assert observed["checks"] == "pending"
    assert observed["missing_required_checks"] == ["frontend", "pre-commit", "gitleaks"]


def test_merged_pr_uses_merge_commit_not_old_preview(tmp_path):
    def runner(command, **_kwargs):
        joined = " ".join(command)
        if command[:3] == ["gh", "pr", "view"]:
            return _completed(
                {
                    "number": 127,
                    "url": "https://github.example/pr/127",
                    "state": "MERGED",
                    "isDraft": False,
                    "headRefOid": "old-pr-head",
                    "mergeCommit": {"oid": "main-merge-sha"},
                    "mergeStateStatus": "UNKNOWN",
                    "statusCheckRollup": [
                        {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "frontend", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "pre-commit", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "gitleaks", "status": "COMPLETED", "conclusion": "SUCCESS"},
                    ],
                }
            )
        if "/branches/main" in joined:
            return _completed({"commit": {"sha": "main-merge-sha"}})
        if "/commits/main-merge-sha/check-runs" in joined:
            return _completed(
                {
                    "check_runs": [
                        {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "frontend", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "pre-commit", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "gitleaks", "status": "COMPLETED", "conclusion": "SUCCESS"},
                    ]
                }
            )
        if "/commits/main-merge-sha/status" in joined:
            return _completed({"statuses": []})
        if "deployments?sha=main-merge-sha" in joined:
            return _completed([])
        raise AssertionError(f"unexpected command: {command}")

    observed = harness.collect_github_observed(pr="127", repository="ahdithanu/buildsignals", runner=runner)
    assert observed["head_sha"] == "main-merge-sha"
    assert observed["pr_head_sha"] == "old-pr-head"
    assert observed["release_source"] == "merge_commit"
    state = harness.ReleaseState(tmp_path / "state.json")
    state.data.update({"head_sha": "main-merge-sha", "events": [], "repair_attempts": {}, "phase": "reconcile"})
    harness.apply_expected_target(state, "production")
    assert harness.reconcile(harness.ReleaseState(tmp_path / "state.json"), observed) == "waiting"
    assert json.loads((tmp_path / "state.json").read_text())["waiting_reason"] == "deployment missing"


def test_pr127_observed_old_success_is_superseded_by_current_main(tmp_path):
    pr127_merge = "8c1c11a0bde172abe73d7c8c259e28bb2915bceb"
    current_main = "56edd81f126c04f4bf46213723efb31da73ee4f7"

    def runner(command, **_kwargs):
        joined = " ".join(command)
        if command[:3] == ["gh", "pr", "view"]:
            return _completed(
                {
                    "number": 127,
                    "url": "https://github.com/ahdithanu/buildsignals/pull/127",
                    "state": "MERGED",
                    "isDraft": False,
                    "headRefOid": "14bfaa5dbf56b067fadbe562eabbd8adf2fb8876",
                    "mergeCommit": {"oid": pr127_merge},
                    "mergeStateStatus": "UNKNOWN",
                    "statusCheckRollup": [],
                }
            )
        if "/branches/main" in joined:
            return _completed({"commit": {"sha": current_main}})
        if f"/commits/{pr127_merge}/check-runs" in joined:
            return _completed(
                {
                    "check_runs": [
                        {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "frontend", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "pre-commit", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "gitleaks", "status": "COMPLETED", "conclusion": "SUCCESS"},
                    ]
                }
            )
        if f"/commits/{pr127_merge}/status" in joined:
            return _completed({"statuses": []})
        if f"deployments?sha={pr127_merge}" in joined:
            return _completed(
                [
                    {
                        "id": 6837962865,
                        "environment": "Production",
                        "statuses_url": "https://api.github.com/repos/ahdithanu/buildsignals/deployments/6837962865/statuses",
                    }
                ]
            )
        if "/deployments/6837962865/statuses" in joined:
            return _completed(
                [
                    {
                        "id": 19236610072,
                        "state": "success",
                        "target_url": "https://buildsignal-7j1pmxxf3-ahdi-s-projects.vercel.app",
                    }
                ]
            )
        raise AssertionError(f"unexpected command: {command}")

    observed = harness.collect_github_observed(pr="127", repository="ahdithanu/buildsignals", runner=runner)
    assert observed["head_sha"] == pr127_merge
    assert observed["current_default_sha"] == current_main
    assert observed["deployment_status"] == "ready"

    state = harness.ReleaseState(tmp_path / "state.json")
    state.data.update({"head_sha": pr127_merge, "events": [], "repair_attempts": {}, "phase": "reconcile"})
    harness.apply_expected_target(state, "production")
    assert harness.reconcile(harness.ReleaseState(tmp_path / "state.json"), observed) == "failure"
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["failure_reason"] == "superseded by current default branch"
    assert data["events"][-1]["detail"]["current_default_sha"] == current_main


def test_merged_pr_failed_main_production_deployment_fails(tmp_path):
    state = harness.ReleaseState(tmp_path / "state.json")
    state.data.update({"head_sha": "main-merge-sha", "events": [], "repair_attempts": {}, "phase": "reconcile"})
    harness.apply_expected_target(state, "production")
    observed = {
        "head_sha": "main-merge-sha",
        "pr_head_sha": "old-pr-head",
        "release_source": "merge_commit",
        "checks": "passed",
        "deployment_id": "prod-1",
        "deployment_target": "production",
        "deployment_status": "failed",
    }
    assert harness.reconcile(harness.ReleaseState(tmp_path / "state.json"), observed) == "failure"
    assert json.loads((tmp_path / "state.json").read_text())["failure_reason"] == "deployment failed"


def test_unknown_deployment_target_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "current_git_ref", lambda: ("feature/release", "sha-1"))
    state = harness.ReleaseState(tmp_path / "state.json")
    state.begin(pr="133", dry_run=True)
    observed = harness.collect_github_observed(
        pr="133",
        repository="ahdithanu/buildsignals",
            runner=_runner_for(
            rollup=[
                {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "frontend", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "pre-commit", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "gitleaks", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ],
            deployments=[{"id": 4444, "environment": None}],
        ),
    )
    assert harness.reconcile(state, observed) == "failure"
    assert json.loads((tmp_path / "state.json").read_text())["failure_reason"] == "deployment target unknown"


def test_expected_deployment_target_can_be_set_before_first_reconcile(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "current_git_ref", lambda: ("feature/release", "sha-1"))
    state = harness.ReleaseState(tmp_path / "state.json")
    state.begin(pr="135", dry_run=True)
    harness.apply_expected_target(state, "production")
    assert harness.reconcile(
        harness.ReleaseState(tmp_path / "state.json"),
        {"head_sha": "sha-1", "checks": "passed", "deployment_id": "dep-1", "deployment_target": "Preview"},
    ) == "failure"
    assert json.loads((tmp_path / "state.json").read_text())["failure_reason"] == "deployment target mismatch"


def test_repair_budget_is_bounded(tmp_path):
    state = harness.ReleaseState(tmp_path / "state.json")
    assert state.repair_budget("frontend-npm-ci", max_attempts=2) == (True, 1)
    assert harness.ReleaseState(tmp_path / "state.json").repair_budget("frontend-npm-ci", max_attempts=2) == (True, 2)
    assert harness.ReleaseState(tmp_path / "state.json").repair_budget("frontend-npm-ci", max_attempts=2) == (False, 2)
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["phase"] == "failure"
    assert data["failure_reason"] == "repair budget exhausted"


def test_lock_rejects_second_owner(tmp_path):
    lock_path = tmp_path / "harness.lock"
    with harness.release_lock(lock_path, "owner-1"):
        with pytest.raises(RuntimeError, match="already held"):
            with harness.release_lock(lock_path, "owner-2"):
                pass


def test_stale_lock_metadata_is_reclaimed_when_no_process_holds_lock(tmp_path):
    lock_path = tmp_path / "harness.lock"
    stale_time = "2026-01-01T00:00:00+00:00"
    lock_path.write_text(json.dumps({"owner": "dead-worker", "acquired_at": stale_time}))
    with harness.release_lock(lock_path, "owner-2", stale_seconds=1):
        payload = json.loads(lock_path.read_text())
        assert payload["owner"] == "owner-2"
        assert payload["stale_reclaimed"] is True


def test_mutating_adapter_calls_fail_closed():
    with pytest.raises(PermissionError):
        harness.assert_read_only("POST", authorized_mutation=False)
    harness.assert_read_only("POST", authorized_mutation=True)
    harness.assert_read_only("GET", authorized_mutation=False)


def test_acceptance_is_skipped_without_live_authorization():
    result = harness.demo_acceptance(
        api_base="https://api.example.test",
        expected_backend="sha-1",
        token=None,
        allow_live=False,
    )
    assert result["status"] == "skipped"
    assert "requires --live-acceptance" in result["reason"]


def test_smoke_script_runner_strips_secret_environment(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setenv("SMOKE_PASSWORD", "secret-password")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr(harness.subprocess, "run", fake_run)
    result = harness.run_smoke_script("https://api.example.test", frontend="https://app.example.test")
    assert result["passed"] is True
    assert captured["env"]["BASE"] == "https://api.example.test"
    assert captured["env"]["FRONTEND"] == "https://app.example.test"
    assert "SMOKE_PASSWORD" not in captured["env"]
    assert "GITHUB_TOKEN" not in captured["env"]


def test_atomic_write_preserves_previous_state_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text('{"phase": "old"}\n')

    def fail_replace(_src, _dst):
        raise OSError("simulated crash")

    monkeypatch.setattr(harness.os, "replace", fail_replace)
    with pytest.raises(OSError):
        harness._write_json_atomic(path, {"phase": "new"})
    assert json.loads(path.read_text()) == {"phase": "old"}


def test_secret_redaction_covers_keys_and_string_values(tmp_path):
    harness._write_json_atomic(
        tmp_path / "state.json",
        {
            "access_token": "abc",
            "note": "Authorization bearer should not land in state",
            "nested": [{"password": "pw"}],
        },
    )
    text = (tmp_path / "state.json").read_text()
    assert "abc" not in text
    assert "bearer" not in text.lower()
    assert "pw" not in text
    assert "[redacted]" in text


def test_watch_reconciles_pending_across_cycles(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "current_git_ref", lambda: ("feature/release", "sha-1"))
    state = harness.ReleaseState(tmp_path / "state.json")
    state.begin(pr="134", dry_run=True)
    observations = iter(
        [
            {"head_sha": "sha-1", "checks": "pending", "run_id": "run-1"},
            {"head_sha": "sha-1", "checks": "passed"},
        ]
    )
    monkeypatch.setattr(harness, "collect_observed", lambda _args, _state: next(observations))
    monkeypatch.setattr(harness.time, "sleep", lambda _seconds: None)
    args = type("Args", (), {"max_cycles": 2, "interval_seconds": 0})()
    assert harness.watch(harness.ReleaseState(tmp_path / "state.json"), args) == "ready_for_acceptance"
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["phase"] == "ready_for_acceptance"


def _work_args(**overrides):
    values = {
        "task": "fix frontend npm ci",
        "observed_json": None,
        "live_github": False,
        "repository": "ahdithanu/buildsignals",
        "main_branch": "main",
        "pr": None,
        "expected_deployment_target": None,
        "repair_executor": "codex-local-repair",
        "validation_command": "harness-validation",
        "max_repair_attempts": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_repair_executor_runs_for_repairable_failure_and_triggers_revalidation(tmp_path, monkeypatch):
    state = harness.ReleaseState(tmp_path / "state.json")
    state.data.update({"head_sha": "sha-1", "events": [], "repair_attempts": {}, "phase": "reconcile"})
    observations = iter(
        [
            {"head_sha": "sha-1", "checks": "failed", "run_id": "run-1"},
        ]
    )
    commands = []

    monkeypatch.setattr(harness, "collect_observed", lambda _args, _state: next(observations))
    monkeypatch.setattr(harness, "run_codex_repair", lambda task: commands.append(f"repair:{task}") or {"command": "codex-local-repair", "passed": True, "returncode": 0})
    monkeypatch.setattr(harness, "run_supported_command", lambda name: commands.append(name) or {"command": name, "passed": True, "returncode": 0})
    phase = harness.drive_product_task(state, _work_args())
    assert phase == "waiting"
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["repair_attempts"]["fix frontend npm ci"] == 1
    assert data["work"]["phase"] == "validation_passed"
    assert commands == ["repair:fix frontend npm ci", "harness-validation"]
    assert data["waiting_reason"] == "repair validated locally; external reconciliation required"


def test_waiting_never_consumes_repair_attempts(tmp_path, monkeypatch):
    state = harness.ReleaseState(tmp_path / "state.json")
    state.data.update({"head_sha": "sha-1", "events": [], "repair_attempts": {}, "phase": "reconcile"})
    monkeypatch.setattr(harness, "collect_observed", lambda _args, _state: {"head_sha": "sha-1", "checks": "pending"})
    phase = harness.drive_product_task(state, _work_args())
    data = json.loads((tmp_path / "state.json").read_text())
    assert phase == "waiting"
    assert data["repair_attempts"] == {}


def test_interruption_after_repair_resumes_validation_without_duplicate_mutation(tmp_path, monkeypatch):
    state = harness.ReleaseState(tmp_path / "state.json")
    state.data.update(
        {
            "head_sha": "sha-1",
            "events": [],
            "repair_attempts": {"fix frontend npm ci": 1},
            "phase": "failure",
            "work": {
                "task": "fix frontend npm ci",
                "phase": "repair_executed",
                "last_repair_signature": harness.repair_signature("codex-local-repair", "fix frontend npm ci"),
            },
        }
    )
    state.save()
    commands = []
    monkeypatch.setattr(harness, "collect_observed", lambda _args, _state: {"head_sha": "sha-1", "checks": "pending"})
    monkeypatch.setattr(harness, "run_codex_repair", lambda task: commands.append(f"repair:{task}") or {"command": "codex-local-repair", "passed": True, "returncode": 0})
    monkeypatch.setattr(harness, "run_supported_command", lambda name: commands.append(name) or {"command": name, "passed": True, "returncode": 0})
    phase = harness.drive_product_task(harness.ReleaseState(tmp_path / "state.json"), _work_args())
    assert phase == "waiting"
    assert commands == ["harness-validation"]
    assert json.loads((tmp_path / "state.json").read_text())["repair_attempts"]["fix frontend npm ci"] == 1


def test_missing_repair_executor_blocks_and_preserves_task(tmp_path, monkeypatch):
    state = harness.ReleaseState(tmp_path / "state.json")
    state.data.update({"head_sha": "sha-1", "events": [], "repair_attempts": {}, "phase": "reconcile"})
    monkeypatch.setattr(harness, "collect_observed", lambda _args, _state: {"head_sha": "sha-1", "checks": "failed"})
    phase = harness.drive_product_task(state, _work_args(repair_executor=None))
    data = json.loads((tmp_path / "state.json").read_text())
    assert phase == "blocked"
    assert data["work"]["task"] == "fix frontend npm ci"
    assert data["blocker_reason"] == "repair executor approval required"


def test_codex_repair_environment_strips_external_credentials(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-secret")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "aws-secret")
    monkeypatch.setenv("VERCEL_TOKEN", "vercel-secret")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")
    env = harness._clean_repair_env()
    assert "GITHUB_TOKEN" not in env
    assert "AWS_ACCESS_KEY_ID" not in env
    assert "VERCEL_TOKEN" not in env
    assert "DATABASE_URL" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["AWS_EC2_METADATA_DISABLED"] == "true"
    assert env["GH_CONFIG_DIR"].endswith("empty-gh-config")


def test_browser_gate_required_blocks_api_only_completion(tmp_path, monkeypatch):
    state = harness.ReleaseState(tmp_path / "state.json")
    state.data.update({"head_sha": "sha-1", "external": {"head_sha": "sha-1"}, "events": [], "repair_attempts": {}})
    state.save()
    result = _run(
        tmp_path,
        "acceptance",
        "--require-browser-gate",
    )
    assert result.returncode == 2
    data = _state(tmp_path)
    assert data["phase"] == "acceptance_blocked"
    assert data["acceptance"]["status"] == "blocked"
    assert data["acceptance"]["release_identity"]["head_sha"] == "sha-1"


def test_acceptance_blocks_superseded_release_identity(tmp_path):
    state = harness.ReleaseState(tmp_path / "state.json")
    state.data.update(
        {
            "head_sha": "old-main",
            "phase": "ready_for_acceptance",
            "external": {
                "head_sha": "old-main",
                "current_default_sha": "new-main",
                "deployment_id": "dep-old",
                "deployment_target": "production",
                "deployment_status": "ready",
            },
            "events": [],
            "repair_attempts": {},
        }
    )
    state.save()
    result = _run(tmp_path, "acceptance", "--run-browser-gate")
    assert result.returncode == 2
    data = _state(tmp_path)
    assert data["acceptance"]["reason"] == "durable release SHA is not the current default branch SHA"


def _product_payloads():
    parcel_coverage = {
        "readiness": {
            "total_source_count": 2,
            "active_source_count": 2,
            "disabled_source_count": 0,
            "stored_records": 20,
            "geocoded_records": 20,
            "empty_source_count": 0,
            "stale_collection_source_count": 0,
            "stale_source_date_source_count": 0,
            "sources_with_unknown_source_dates": 0,
            "sources_with_future_source_dates": 0,
        },
        "readiness_status_counts": {
            "fresh": 2,
            "empty": 0,
            "disabled": 0,
            "stale_collection": 0,
            "stale_source_date": 0,
            "unknown_source_date": 0,
        },
        "sources": [
            {"source_key": "city_a_parcels", "readiness_status": "fresh"},
            {"source_key": "county_b_parcels", "readiness_status": "fresh"},
        ],
    }
    map_readiness = {
        "ready_for_ranked_map": True,
        "parcels": 20,
        "geocoded_parcels": 20,
        "geocoded_signals": 4,
        "saved_searches": 1,
    }
    heatmap = {
        "method_version": "zip3-opportunity-heat-v1",
        "for_sale_semantics": {"verified_for_sale": "Requires source evidence"},
        "items": [
            {
                "zip3": "787",
                "latitude": 30.2672,
                "longitude": -97.7431,
                "latest_signal_at": "2026-10-01T00:00:00Z",
                "sample_signals": [{"id": "signal-1", "source_url": "https://source.example"}],
                "sample_parcels": [],
            }
        ],
    }
    insights = [
        {
            "insight_type": "zip3_momentum",
            "title": "ZIP3 787 pre-approval momentum",
            "description": "3 source-backed pre-approval records in the last 30 days",
            "priority": "high",
            "time_window": {"start": "2026-09-01", "end": "2026-10-01"},
            "source_records": [{"id": "permit-1", "source_url": "https://source.example"}],
        }
    ]
    return parcel_coverage, map_readiness, heatmap, insights


def test_product_production_evidence_passes_only_with_complete_live_contract():
    parcel_coverage, map_readiness, heatmap, insights = _product_payloads()
    result = harness.evaluate_product_production_evidence(
        parcel_coverage=parcel_coverage,
        map_readiness_payload=map_readiness,
        heatmap_payload=heatmap,
        insights_payload=insights,
    )
    assert result["status"] == "passed"
    assert all(check["passed"] for check in result["checks"])


def test_product_production_evidence_blocks_missing_unlocated_or_stale_parcels():
    parcel_coverage, map_readiness, heatmap, insights = _product_payloads()
    parcel_coverage["readiness"].update(
        geocoded_records=18,
        empty_source_count=1,
        stale_source_date_source_count=1,
        sources_with_unknown_source_dates=1,
    )
    parcel_coverage["sources"][1]["readiness_status"] = "stale_source_date"
    result = harness.evaluate_product_production_evidence(
        parcel_coverage=parcel_coverage,
        map_readiness_payload=map_readiness,
        heatmap_payload=heatmap,
        insights_payload=insights,
    )
    coverage = next(check for check in result["checks"] if check["name"] == "parcel coverage completeness")
    assert result["status"] == "blocked"
    assert coverage["unlocated_records"] == 2
    assert coverage["empty_sources"] == 1
    assert coverage["stale_source_date_sources"] == 1
    assert coverage["unknown_source_date_sources"] == 1
    assert coverage["blocking_sources"] == ["county_b_parcels"]


def test_product_evidence_uses_all_manifest_sources_as_denominator():
    parcel_coverage, map_readiness, heatmap, insights = _product_payloads()
    manifest = {
        "manifest_digest": "digest-1",
        "source_count": 3,
        "sources": [
            {
                "source_key": "city_a_parcels",
                "status": "production_catalog",
                "configured_active": True,
                "known_total_records": 10,
                "extraction_completion_evidence": "snapshot complete",
            },
            {
                "source_key": "county_b_parcels",
                "status": "production_catalog",
                "configured_active": True,
                "known_total_records": 10,
                "extraction_completion_evidence": "snapshot complete",
            },
            {
                "source_key": "held_statewide_parcels",
                "status": "legal_hold",
                "configured_active": False,
                "known_total_records": None,
                "extraction_completion_evidence": None,
            },
        ],
    }
    result = harness.evaluate_product_production_evidence(
        parcel_coverage=parcel_coverage,
        map_readiness_payload=map_readiness,
        heatmap_payload=heatmap,
        insights_payload=insights,
        parcel_source_manifest=manifest,
    )
    coverage = next(check for check in result["checks"] if check["name"] == "parcel coverage completeness")
    assert result["status"] == "blocked"
    assert coverage["missing_manifest_sources"] == ["held_statewide_parcels"]
    assert coverage["held_manifest_sources"] == ["held_statewide_parcels"]


def test_product_evidence_blocks_unknown_totals_and_completion_even_when_ingested_green():
    parcel_coverage, map_readiness, heatmap, insights = _product_payloads()
    manifest = {
        "manifest_digest": "digest-2",
        "source_count": 2,
        "sources": [
            {
                "source_key": "city_a_parcels",
                "status": "production_catalog",
                "configured_active": True,
                "known_total_records": None,
                "extraction_completion_evidence": "snapshot complete",
            },
            {
                "source_key": "county_b_parcels",
                "status": "production_catalog",
                "configured_active": True,
                "known_total_records": 10,
                "extraction_completion_evidence": None,
            },
        ],
    }
    result = harness.evaluate_product_production_evidence(
        parcel_coverage=parcel_coverage,
        map_readiness_payload=map_readiness,
        heatmap_payload=heatmap,
        insights_payload=insights,
        parcel_source_manifest=manifest,
    )
    coverage = next(check for check in result["checks"] if check["name"] == "parcel coverage completeness")
    assert result["status"] == "blocked"
    assert coverage["unknown_total_sources"] == ["city_a_parcels"]
    assert coverage["incomplete_extraction_sources"] == ["county_b_parcels"]


def test_product_evidence_accepts_live_full_source_completion_evidence():
    parcel_coverage, map_readiness, heatmap, insights = _product_payloads()
    for source in parcel_coverage["sources"]:
        source["completion_evidence"] = {
            "full_source_completed": True,
            "completion_kind": "full_source_snapshot_completed",
        }
    manifest = {
        "manifest_digest": "digest-3",
        "source_count": 2,
        "sources": [
            {
                "source_key": "city_a_parcels",
                "status": "production_catalog",
                "configured_active": True,
                "known_total_records": 10,
                "extraction_completion_evidence": None,
            },
            {
                "source_key": "county_b_parcels",
                "status": "production_catalog",
                "configured_active": True,
                "known_total_records": 10,
                "extraction_completion_evidence": None,
            },
        ],
    }
    result = harness.evaluate_product_production_evidence(
        parcel_coverage=parcel_coverage,
        map_readiness_payload=map_readiness,
        heatmap_payload=heatmap,
        insights_payload=insights,
        parcel_source_manifest=manifest,
    )
    assert result["status"] == "passed"


def test_build_parcel_source_manifest_counts_repository_sources():
    manifest = harness.build_parcel_source_manifest()
    assert manifest["production_source_count"] >= 41
    assert manifest["source_count"] >= manifest["production_source_count"]
    assert "manifest_digest" in manifest
    assert all(source["source_key"] for source in manifest["sources"])


def test_product_production_evidence_blocks_bad_heatmap_and_untraceable_insights():
    parcel_coverage, map_readiness, heatmap, insights = _product_payloads()
    heatmap["items"].append({**heatmap["items"][0], "latitude": 200})
    insights[0].pop("source_records")
    result = harness.evaluate_product_production_evidence(
        parcel_coverage=parcel_coverage,
        map_readiness_payload=map_readiness,
        heatmap_payload=heatmap,
        insights_payload=insights,
    )
    heatmap_check = next(check for check in result["checks"] if check["name"] == "heatmap aggregation and explanations")
    insight_check = next(check for check in result["checks"] if check["name"] == "traceable deterministic insights")
    assert result["status"] == "blocked"
    assert heatmap_check["duplicate_zip3"] == ["787"]
    assert heatmap_check["coordinate_failures"] == ["787"]
    assert insight_check["untraceable_insights"] == ["zip3_momentum"]


def test_live_product_gate_requires_token_and_does_not_use_local_fixtures():
    result = harness.product_production_acceptance(
        api_base="https://api.example.test",
        token=None,
        allow_live=True,
    )
    assert result["status"] == "blocked"
    assert "read-only bearer token" in result["reason"]


def test_codex_repair_uses_supported_cli_argument_order(monkeypatch, tmp_path):
    captured = {}
    fake_codex = tmp_path / "codex"
    fake_codex.write_text("#!/bin/sh\nexit 0\n")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(harness.shutil, "which", lambda name: str(fake_codex) if name == "codex" else None)
    monkeypatch.setattr(harness.subprocess, "run", fake_run)
    result = harness.run_codex_repair("repair harmless fixture")
    assert result["passed"] is True
    assert captured["command"][:6] == [str(fake_codex), "--sandbox", "workspace-write", "--ask-for-approval", "never", "exec"]
    assert "--output-last-message" in captured["command"]


def test_cli_status_and_repair_budget(tmp_path):
    started = _run(tmp_path, "start", "--pr", "132")
    assert started.returncode == 0, started.stderr
    status = _run(tmp_path, "status")
    assert status.returncode == 0
    assert json.loads(status.stdout)["pr"] == "132"
    assert _run(tmp_path, "resume", "--record-repair", "checks", "--max-repair-attempts", "1").returncode == 0
    exhausted = _run(tmp_path, "resume", "--record-repair", "checks", "--max-repair-attempts", "1")
    assert exhausted.returncode == 2
    assert _state(tmp_path)["failure_reason"] == "repair budget exhausted"
