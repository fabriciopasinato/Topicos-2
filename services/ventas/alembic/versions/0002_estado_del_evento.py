"""Estado del evento en el inventario: fecha de inicio, cancelacion y version

Copia de lo que decide eventos (su duenio): ventas la usa para cerrar la venta
de eventos cancelados o ya iniciados sin consultar a eventos.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: los inventarios recibidos antes de este cambio no tienen fecha
    # y siguen vendiendose como antes.
    op.add_column("inventario_eventos", sa.Column("fecha_inicio", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "inventario_eventos",
        sa.Column("cancelado", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "inventario_eventos",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("inventario_eventos", "version")
    op.drop_column("inventario_eventos", "cancelado")
    op.drop_column("inventario_eventos", "fecha_inicio")
