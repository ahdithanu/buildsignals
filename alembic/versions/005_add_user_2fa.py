"""Add TOTP 2FA columns to users.

Revision ID: 005_add_user_2fa
Revises: 004
Create Date: 2026-06-07

Adds `totp_secret` (base32 shared secret, NULL until /auth/2fa/setup runs)
and `totp_enabled` (boolean, flipped to True only after the user confirms
enrollment by submitting a valid TOTP code to /auth/2fa/verify).

Existing rows get totp_enabled=false / totp_secret=NULL — i.e. nothing
changes for users who never enroll, and /auth/login keeps working without
a TOTP code for them.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_add_user_2fa"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("totp_secret", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "totp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
