from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.bench import redact_sensitive_text  # noqa: E402


DEFAULT_PATHS = [ROOT / "eval" / "results.csv", ROOT / "eval" / "results.md"]


def redact_file(path: Path) -> bool:
    original = path.read_text()
    redacted = redact_sensitive_text(original)
    if redacted == original:
        return False
    path.write_text(redacted)
    return True


def main(argv: list[str] | None = None) -> int:
    paths = [Path(arg) for arg in argv] if argv else DEFAULT_PATHS
    changed = [path for path in paths if path.exists() and redact_file(path)]
    for path in changed:
        print(f"redacted {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
