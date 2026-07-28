"""Merge password-reset and parcel ingestion migration heads.

Revision ID: 20260728_0001
Revises: 006_add_password_reset_tokens, 20260726_0001
Create Date: 2026-07-28
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "20260728_0001"
down_revision: Union[str, Sequence[str], None] = (
    "006_add_password_reset_tokens",
    "20260726_0001",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
