"""The portable agent context command is safe and machine-readable."""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_context_json_is_read_only_and_has_resume_contract():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/agent_context.py", "--json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    context = json.loads(result.stdout)
    assert context["canonical_instructions"] == "AGENTS.md"
    assert context["handoff"] == "docs/agent-handoff.md"
    assert "backend_tests" in context["commands"]
    assert "frontend_build" in context["commands"]
    assert "SECRET_KEY" not in result.stdout
    assert "OPENROUTER_API_KEY" not in result.stdout

