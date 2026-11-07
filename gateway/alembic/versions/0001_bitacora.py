"""Tabla de bitacora de solicitudes

Revision ID: 0001
Revises:
Create Date: 2026-11-07
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bitacora",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("metodo", sa.String(10), nullable=False),
        sa.Column("ruta", sa.String(500), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("duracion_ms", sa.Float(), nullable=False),
    )
    op.create_index("ix_bitacora_timestamp", "bitacora", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_bitacora_timestamp", table_name="bitacora")
    op.drop_table("bitacora")
