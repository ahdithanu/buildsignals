"""Add users.token_version for refresh-token revocation.

Revision ID: 004
Revises: 003
Create Date: 2026-06-07

Adds an integer counter to the users table. Bumped by POST /auth/logout-all
to invalidate every outstanding refresh cookie for the user: each refresh
JWT carries the version it was minted at as a `tv` claim, and /auth/refresh
rejects any cookie whose `tv` no longer matches the row.

Existing rows default to 0 (server_default), matching the `tv` claim that
tokens minted before this migration implicitly carry (decoded as 0 via
`claims.get("tv", 0)`).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
