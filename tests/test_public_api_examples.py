"""Public API examples should stay executable as docs evolve."""

from __future__ import annotations

import py_compile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXAMPLE = ROOT / "docs" / "examples" / "public_api_client.py"
TYPESCRIPT_EXAMPLE = ROOT / "docs" / "examples" / "public_api_client.ts"


def test_python_public_api_example_compiles() -> None:
    py_compile.compile(str(PYTHON_EXAMPLE), doraise=True)


def test_typescript_public_api_example_typechecks() -> None:
    result = subprocess.run(
        [
            "npx",
            "tsc",
            "--noEmit",
            "--target",
            "ES2022",
            "--module",
            "NodeNext",
            "--moduleResolution",
            "NodeNext",
            "--skipLibCheck",
            "--types",
            "node",
            str(TYPESCRIPT_EXAMPLE),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
