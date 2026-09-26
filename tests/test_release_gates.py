"""Release checks must propagate tool failures instead of reporting false green."""
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _step(workflow, job, name):
    config = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text())
    return next(step for step in config["jobs"][job]["steps"] if step.get("name") == name)


@pytest.mark.parametrize("name", [
    "Alembic drift check (no un-migrated model changes)",
    "PostgreSQL schema drift check",
])
@pytest.mark.parametrize("exit_code", [0, 42])
def test_schema_gate_propagates_success_and_failure(tmp_path, name, exit_code):
    step = _step("ci.yml", "test", name)
    assert not step.get("continue-on-error", False)
    assert "python -m alembic check" in step["run"]
    executable = tmp_path / "python"
    executable.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    executable.chmod(0o700)
    result = subprocess.run(
        ["/bin/bash", "-e", "-c", step["run"]],
        env={**os.environ, "PATH": str(tmp_path), "TEST_POSTGRES_URL": "postgresql://unused"},
        capture_output=True, timeout=5,
    )
    assert result.returncode == exit_code


def test_frontend_audit_gate_covers_development_dependencies(tmp_path):
    step = _step("frontend.yml", "frontend", "Dependency vulnerability gate")
    assert not step.get("continue-on-error", False)
    assert step["run"] == "npm audit --audit-level=moderate"
    executable = tmp_path / "npm"
    executable.write_text("#!/bin/sh\nexit 1\n")
    executable.chmod(0o700)
    result = subprocess.run(["/bin/bash", "-e", "-c", step["run"]],
                            env={**os.environ, "PATH": str(tmp_path)}, timeout=5)
    assert result.returncode == 1


@pytest.mark.parametrize("blueprint,name", [
    ("render.yaml", "dealsignal-frontend"),
    ("render-staging.yaml", "dealsignal-frontend-staging"),
])
def test_render_build_uses_ci_lockfile(blueprint, name):
    config = yaml.safe_load((ROOT / blueprint).read_text())
    frontend = next(service for service in config["services"] if service["name"] == name)
    assert frontend["buildCommand"] == "npm ci && npm run build"
    node = next(value for value in frontend["envVars"] if value["key"] == "NODE_VERSION")
    assert node["value"].startswith("22.")


@pytest.mark.parametrize("workflow,job", [("frontend.yml", "frontend"), ("e2e.yml", "e2e")])
def test_browser_ci_uses_tested_node_major(workflow, job):
    assert _step(workflow, job, "Set up Node")["with"]["node-version"] == "22"
