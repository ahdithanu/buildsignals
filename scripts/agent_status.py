"""Offline, read-only starting point for agents resuming this repository."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
    "docs/agent-handoff.md",
    "docs/agent-onboarding.md",
    "docs/templates/agent-handoff.md",
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if shared handoff files are missing or adapters drift")
    args = parser.parse_args()
    print("BuildSignals agent status (offline; no environment values or cloud calls)")
    print(f"Branch: {git('rev-parse', '--abbrev-ref', 'HEAD')}")
    print(f"HEAD: {git('log', '-1', '--format=%h %s')}")
    print(f"Upstream: {git('rev-parse', '--abbrev-ref', '@{upstream}')}")
    print("Working tree:\n" + (git("status", "--short") or "clean"))
    print("Recent commits:\n" + git("log", "-5", "--oneline"))
    problems = []
    for name in REQUIRED:
        exists = (ROOT / name).is_file()
        print(f"{'OK' if exists else 'MISSING'} {name}")
        if not exists:
            problems.append(name)
    for name in ("CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md"):
        path = ROOT / name
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            if "AGENTS.md" not in content or "docs/agent-handoff.md" not in content:
                problems.append(f"{name}: missing shared instruction/handoff reference")
    print("Tools: " + ", ".join(
        f"{tool}={'available' if shutil.which(tool) else 'not found'}"
        for tool in ("python3", "node", "npm", "git", "gh", "aws", "vercel", "claude")
    ))
    print("Read docs/agent-handoff.md next. Production observations are dated, not live checks.")
    if args.check and problems:
        print("Handoff check failed: " + "; ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
