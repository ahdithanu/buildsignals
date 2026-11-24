"""Offline, read-only starting point for agents resuming this repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
FORGEOS_PROFILE = "docs/forgeos-project-profile.md"
FORGEOS_WORKFLOW = "docs/forgeos-delivery-loop.md"
FORGEOS_MANIFEST = ".forgeos/adoption.json"
REQUIRED = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
    "docs/agent-handoff.md",
    "docs/agent-onboarding.md",
    "docs/templates/agent-handoff.md",
    FORGEOS_PROFILE,
    FORGEOS_WORKFLOW,
    FORGEOS_MANIFEST,
)


def valid_source_path(value: object) -> bool:
    if not isinstance(value, str) or not value or any(
        char in "\\:" or ord(char) < 32 or ord(char) == 127 for char in value
    ):
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute() and bool(path.parts) and ".." not in path.parts
        and path.as_posix() == value
    )


def forgeos_problems(source_root: Path | None) -> list[str]:
    manifest_path = ROOT / FORGEOS_MANIFEST
    if not manifest_path.is_file():
        return []  # Missing required files are reported by the shared presence check.
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"{FORGEOS_MANIFEST}: invalid JSON or unreadable file"]
    if not isinstance(manifest, dict):
        return [f"{FORGEOS_MANIFEST}: expected an object"]
    problems = []
    for key, expected in (
        ("schema_version", 1), ("project", "BuildSignals"),
        ("profile", FORGEOS_PROFILE), ("workflow", FORGEOS_WORKFLOW),
    ):
        value = manifest.get(key)
        if type(value) is not type(expected) or value != expected:
            problems.append(f"{FORGEOS_MANIFEST}: {key} must be {expected!r}")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        return [*problems, f"{FORGEOS_MANIFEST}: sources must be a nonempty list"]
    if source_root is not None:
        try:
            source_root = source_root.resolve(strict=True)
            if not source_root.is_dir():
                raise ValueError("not a directory")
        except (OSError, RuntimeError, ValueError):
            return [*problems, "ForgeOS source root: missing or unreadable directory"]
    for index, source in enumerate(sources):
        label = f"{FORGEOS_MANIFEST}: sources[{index}]"
        if not isinstance(source, dict):
            problems.append(f"{label}: expected an object with path and sha256")
            continue
        name, digest = source.get("path"), source.get("sha256")
        if not valid_source_path(name):
            problems.append(f"{label}: path must be a canonical relative path without traversal")
            continue
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            problems.append(f"{label}: sha256 must be 64 lowercase hex characters")
            continue
        if source_root is not None:
            try:
                path = (source_root / name).resolve(strict=True)
                if not path.is_relative_to(source_root) or not path.is_file():
                    raise ValueError("not a file within source root")
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, RuntimeError, ValueError):
                problems.append(f"{label}: {name}: missing, unreadable, or outside ForgeOS root")
                continue
            if actual != digest:
                problems.append(f"{label}: {name}: sha256 drift")
            else:
                print(f"OK ForgeOS source {name} (sha256 verified)")
    return problems


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if shared handoff files or ForgeOS adoption drift")
    parser.add_argument(
        "--forgeos-root", type=Path, metavar="PATH",
        help="Explicitly verify pinned source bytes under PATH; never discovered automatically",
    )
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
    agents_path = ROOT / "AGENTS.md"
    if agents_path.is_file():
        content = agents_path.read_text(encoding="utf-8")
        for name in (FORGEOS_PROFILE, FORGEOS_WORKFLOW):
            if name not in content:
                problems.append(f"AGENTS.md: missing {name} reference")
    problems.extend(forgeos_problems(args.forgeos_root))
    print("Tools: " + ", ".join(
        f"{tool}={'available' if shutil.which(tool) else 'not found'}"
        for tool in ("python3", "node", "npm", "git", "gh", "aws", "vercel", "claude")
    ))
    print("Read docs/agent-handoff.md next. Production observations are dated, not live checks.")
    if (args.check or args.forgeos_root is not None) and problems:
        print("Handoff check failed: " + "; ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
