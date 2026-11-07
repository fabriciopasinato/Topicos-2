"""Inventario, tickets, reservas, ordenes e idempotencia

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
        "inventario_eventos",
        sa.Column("evento_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "reservas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("evento_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("hasta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="activa"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("estado IN ('activa', 'pagada', 'cancelada')", name="ck_reservas_estado"),
    )
    op.create_index("ix_reservas_user_id", "reservas", ["user_id"])
    op.create_table(
        "ordenes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reserva_id", sa.Integer(), sa.ForeignKey("reservas.id"), nullable=False, unique=True),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ordenes_user_id", "ordenes", ["user_id"])
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evento_id", sa.Integer(), nullable=False),
        sa.Column("zona_id", sa.Integer(), nullable=False),
        sa.Column("tipo_zona", sa.String(20), nullable=False),
        sa.Column("fila", sa.String(10), nullable=True),
        sa.Column("numero", sa.Integer(), nullable=True),
        sa.Column("precio", sa.Numeric(10, 2), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="disponible"),
        sa.Column("reserva_id", sa.Integer(), sa.ForeignKey("reservas.id"), nullable=True),
        sa.Column("reservado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orden_id", sa.Integer(), sa.ForeignKey("ordenes.id"), nullable=True),
        sa.CheckConstraint("estado IN ('disponible', 'reservado', 'vendido')", name="ck_tickets_estado"),
        sa.CheckConstraint("tipo_zona IN ('numerada', 'general')", name="ck_tickets_tipo_zona"),
    )
    op.create_index("ix_tickets_evento_id", "tickets", ["evento_id"])
    op.create_index("ix_tickets_zona_estado", "tickets", ["zona_id", "estado"])
    op.create_index("ix_tickets_reserva_id", "tickets", ["reserva_id"])
    op.create_index("ix_tickets_orden_id", "tickets", ["orden_id"])
    op.create_index(
        "uq_tickets_asiento_numerado", "tickets", ["evento_id", "zona_id", "fila", "numero"],
        unique=True, postgresql_where=sa.text("tipo_zona = 'numerada'"),
    )
    op.create_table(
        "orden_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("orden_id", sa.Integer(), sa.ForeignKey("ordenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("precio", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_orden_items_orden_id", "orden_items", ["orden_id"])
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("reserva_id", sa.Integer(), sa.ForeignKey("reservas.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("orden_items")
    op.drop_table("tickets")
    op.drop_table("ordenes")
    op.drop_table("reservas")
    op.drop_table("inventario_eventos")
