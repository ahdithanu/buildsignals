"""Public API examples should stay executable as docs evolve."""

from __future__ import annotations

import json
import py_compile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXAMPLE = ROOT / "docs" / "examples" / "public_api_client.py"
TYPESCRIPT_EXAMPLE = ROOT / "docs" / "examples" / "public_api_client.ts"


def test_python_public_api_example_compiles() -> None:
    py_compile.compile(str(PYTHON_EXAMPLE), doraise=True)


def test_typescript_public_api_example_typechecks(tmp_path: Path) -> None:
    tsconfig = tmp_path / "tsconfig.public-api-example.json"
    tsconfig.write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "module": "NodeNext",
                    "moduleResolution": "NodeNext",
                    "noEmit": True,
                    "skipLibCheck": True,
                    "target": "ES2022",
                },
                "files": [str(TYPESCRIPT_EXAMPLE)],
            }
        )
    )
    result = subprocess.run(
        [
            "npx",
            "tsc",
            "-p",
            str(tsconfig),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
