#!/usr/bin/env python3
"""Print a safe, read-only orientation packet for any coding agent.

The command reports repository metadata and pointers to durable project context.
It never reads environment values, calls external services, or writes files.
Use ``--json`` when another agent harness needs structured output.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"unavailable: {result.stderr.strip()}"
    return result.stdout.strip()


def build_context() -> dict[str, Any]:
    return {
        "repository_root": str(ROOT),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": _git("rev-parse", "HEAD"),
        "working_tree": _git("status", "--short"),
        "recent_commits": _git("log", "--oneline", "-8").splitlines(),
        "canonical_instructions": "AGENTS.md",
        "handoff": "docs/agent-handoff.md",
        "commands": {
            "backend_tests": "pytest -q",
            "backend_lint": "ruff check app/ scripts/ tests/",
            "frontend_tests": "npm run test",
            "frontend_typecheck": "npm run typecheck",
            "frontend_build": "npm run build",
            "browser_tests": "npm run e2e",
        },
        "important_docs": [
            "docs/enterprise_readiness.md",
            "docs/runbooks/deploy.md",
            "docs/runbooks/incident-response.md",
            "docs/secrets.md",
            "docs/runbooks/release-harness.md",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    context = build_context()
    if args.json:
        print(json.dumps(context, indent=2))
        return 0

    print("Build Signals agent context")
    print(f"root: {context['repository_root']}")
    print(f"branch: {context['branch']}")
    print(f"head: {context['head']}")
    print("working tree:")
    print(context["working_tree"] or "clean")
    print("recent commits:")
    for commit in context["recent_commits"]:
        print(f"  {commit}")
    print("read first: AGENTS.md, docs/agent-handoff.md")
    print("next: inspect the handoff, then run the smallest relevant verification")
    return 0


if __name__ == "__main__":
    sys.exit(main())

