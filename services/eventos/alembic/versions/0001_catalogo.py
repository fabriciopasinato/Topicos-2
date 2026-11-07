"""Catalogo: recintos, eventos, sectores, zonas y asientos

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
        "recintos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("direccion", sa.String(300), nullable=False, server_default=""),
    )
    op.create_table(
        "eventos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recinto_id", sa.Integer(), sa.ForeignKey("recintos.id"), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="borrador"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("estado IN ('borrador', 'publicado')", name="ck_eventos_estado"),
    )
    op.create_index("ix_eventos_owner_id", "eventos", ["owner_id"])
    op.create_table(
        "sectores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evento_id", sa.Integer(), sa.ForeignKey("eventos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
    )
    op.create_index("ix_sectores_evento_id", "sectores", ["evento_id"])
    op.create_table(
        "zonas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sector_id", sa.Integer(), sa.ForeignKey("sectores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("capacidad", sa.Integer(), nullable=False),
        sa.Column("precio", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint("tipo IN ('numerada', 'general')", name="ck_zonas_tipo"),
        sa.CheckConstraint("capacidad > 0", name="ck_zonas_capacidad"),
        sa.CheckConstraint("precio >= 0", name="ck_zonas_precio"),
    )
    op.create_index("ix_zonas_sector_id", "zonas", ["sector_id"])
    op.create_table(
        "asientos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("zona_id", sa.Integer(), sa.ForeignKey("zonas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fila", sa.String(10), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.UniqueConstraint("zona_id", "fila", "numero", name="uq_asientos_zona_fila_numero"),
    )
    op.create_index("ix_asientos_zona_id", "asientos", ["zona_id"])


def downgrade() -> None:
    op.drop_table("asientos")
    op.drop_table("zonas")
    op.drop_table("sectores")
    op.drop_table("eventos")
    op.drop_table("recintos")
