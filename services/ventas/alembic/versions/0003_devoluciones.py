"""Tabla de devoluciones de tickets

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devoluciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("orden_item_id", sa.Integer(), sa.ForeignKey("orden_items.id"), nullable=False),
        sa.Column("orden_id", sa.Integer(), sa.ForeignKey("ordenes.id"), nullable=False),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("motivo", sa.String(500), nullable=True),
        sa.Column("nota_resolucion", sa.String(500), nullable=True),
        sa.Column("resuelto_por", sa.Integer(), nullable=True),
        sa.Column("resuelto_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'aprobada', 'rechazada')",
            name="ck_devoluciones_estado",
        ),
    )
    op.create_index("ix_devoluciones_orden_item_id", "devoluciones", ["orden_item_id"])
    op.create_index("ix_devoluciones_orden_id", "devoluciones", ["orden_id"])
    op.create_index("ix_devoluciones_ticket_id", "devoluciones", ["ticket_id"])
    op.create_index("ix_devoluciones_user_id", "devoluciones", ["user_id"])
    op.create_index("ix_devoluciones_estado_created", "devoluciones", ["estado", "created_at"])
    op.create_index(
        "uq_devoluciones_item_activa",
        "devoluciones",
        ["orden_item_id"],
        unique=True,
        postgresql_where=sa.text("estado IN ('pendiente', 'aprobada')"),
    )


def downgrade() -> None:
    op.drop_table("devoluciones")
