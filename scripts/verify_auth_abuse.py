"""Run only the opt-in Redis harness with ambient REDIS_URL disabled."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    environment = {**os.environ, "REDIS_URL": ""}
    os.execve(
        sys.executable,
        [
            sys.executable,
            "-m",
            "pytest",
            "-v",
            "-ra",
            str(root / "tests" / "test_redis_abuse_integration.py"),
            *sys.argv[1:],
        ],
        environment,
    )


if __name__ == "__main__":
    main()
