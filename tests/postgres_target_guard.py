"""Pure accidental-target safeguard, not proof of locality or authorization.

The parent must verify database identity, marker and restricted roles on every
independent connection. A loopback tunnel passes this syntactic URL check.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import RFC_4122, UUID

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


@dataclass(frozen=True)
class SnapshotPostgresTarget:
    url: URL = field(repr=False)
    database: str
    username: str
    marker: str
    run_id: str


def validate_snapshot_test_target(
    url: str, run_id: str, environ: Mapping[str, str],
) -> SnapshotPostgresTarget:
    """Validate explicit test inputs without engines, environment reads, or I/O."""
    message = "Invalid disposable snapshot PostgreSQL test target"
    if (type(url) is not str or type(run_id) is not str
            or re.fullmatch(r"[0-9a-f]{32}", run_id) is None
            or not isinstance(environ, Mapping)):
        raise ValueError(message)
    allowed = False
    try:
        ambient_clear = all(
            type(name) is str
            and (not name.startswith("PG") or (type(value) is str and value == ""))
            for name, value in environ.items()
        )
        identity = UUID(hex=run_id)
        parsed = make_url(url)
        database = f"bs_snapshot_test_{run_id}"
        allowed = (
            ambient_clear and identity.version == 4 and identity.variant == RFC_4122
            and parsed.drivername == "postgresql+psycopg2"
            and parsed.host in {"127.0.0.1", "::1"}
            and parsed.port is not None and 1 <= parsed.port <= 65535
            and bool(parsed.username) and bool(parsed.password)
            and not parsed.query and "?" not in url and parsed.database == database
        )
    except (ArgumentError, ValueError, TypeError, OverflowError):
        allowed = False
    # Raise outside the handler so even exception introspection has no parser
    # context containing connection strings, credentials or ambient values.
    if not allowed:
        raise ValueError(message)
    return SnapshotPostgresTarget(
        url=parsed, database=database, username=parsed.username,
        marker=f"BuildSignals disposable snapshot test:{run_id}", run_id=run_id,
    )
