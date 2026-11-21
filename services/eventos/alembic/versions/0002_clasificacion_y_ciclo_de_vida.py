"""Clasificacion del evento, ciclo de vida y outbox hacia ventas

- tipos_evento: catalogo de tipos (codigo + nombre visible) con los seis
  iniciales. Un tipo nuevo se agrega con otra migracion que inserta la fila.
- organizadores y participantes: entidades minimas, unicas por nombre normalizado.
- eventos: tipo, descripcion, organizador, version / version_aplicada,
  publicado_at y el estado 'cancelado'.
- operaciones_ventas: outbox de reprogramaciones y cancelaciones pendientes.

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

TIPOS_INICIALES = [
    ("recital", "Recital"),
    ("teatro", "Teatro"),
    ("deporte", "Deporte"),
    ("conferencia", "Conferencia"),
    ("festival", "Festival"),
    ("otro", "Otro"),
]


def _catalogo(nombre: str) -> None:
    """organizadores / participantes: `clave` es el nombre normalizado."""
    op.create_table(
        nombre,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("clave", sa.String(200), nullable=False),
        sa.UniqueConstraint("clave", name=f"uq_{nombre}_clave"),
    )


def upgrade() -> None:
    tipos = op.create_table(
        "tipos_evento",
        sa.Column("codigo", sa.String(30), primary_key=True),
        sa.Column("nombre", sa.String(100), nullable=False),
    )
    op.bulk_insert(tipos, [{"codigo": c, "nombre": n} for c, n in TIPOS_INICIALES])

    _catalogo("organizadores")
    _catalogo("participantes")

    op.create_table(
        "evento_participantes",
        sa.Column("evento_id", sa.Integer(), sa.ForeignKey("eventos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("participante_id", sa.Integer(), sa.ForeignKey("participantes.id"), primary_key=True),
    )
    op.create_index("ix_evento_participantes_participante_id", "evento_participantes", ["participante_id"])

    # tipo: el default solo completa los eventos existentes y despues se quita,
    # para que la base tambien exija el tipo en las altas nuevas.
    op.add_column("eventos", sa.Column("tipo", sa.String(30), nullable=False, server_default="otro"))
    op.alter_column("eventos", "tipo", server_default=None)
    op.create_foreign_key("fk_eventos_tipo", "eventos", "tipos_evento", ["tipo"], ["codigo"])
    op.create_index("ix_eventos_tipo", "eventos", ["tipo"])

    op.add_column("eventos", sa.Column("descripcion", sa.Text(), nullable=False, server_default=""))
    # Nullable solo por los eventos existentes: la API lo exige en las altas.
    op.add_column("eventos", sa.Column("organizador_id", sa.Integer(), sa.ForeignKey("organizadores.id"), nullable=True))
    op.create_index("ix_eventos_organizador_id", "eventos", ["organizador_id"])
    op.add_column("eventos", sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("eventos", sa.Column("version_aplicada", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("eventos", sa.Column("publicado_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE eventos SET publicado_at = created_at WHERE estado = 'publicado'")

    op.drop_constraint("ck_eventos_estado", "eventos", type_="check")
    op.create_check_constraint("ck_eventos_estado", "eventos", "estado IN ('borrador', 'publicado', 'cancelado')")

    op.create_table(
        "operaciones_ventas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evento_id", sa.Integer(), sa.ForeignKey("eventos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        sa.Column("proximo_intento_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmada_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("tipo IN ('reprogramar', 'cancelar')", name="ck_operaciones_ventas_tipo"),
        sa.CheckConstraint("estado IN ('pendiente', 'confirmada')", name="ck_operaciones_ventas_estado"),
        sa.CheckConstraint("tipo <> 'reprogramar' OR fecha IS NOT NULL", name="ck_operaciones_ventas_fecha"),
        sa.UniqueConstraint("evento_id", "version", name="uq_operaciones_ventas_evento_version"),
    )
    # El cron busca solo lo pendiente y vencido.
    op.create_index(
        "ix_operaciones_ventas_pendientes", "operaciones_ventas", ["proximo_intento_at"],
        postgresql_where=sa.text("estado = 'pendiente'"),
    )


def downgrade() -> None:
    op.drop_index("ix_operaciones_ventas_pendientes", table_name="operaciones_ventas")
    op.drop_table("operaciones_ventas")

    op.drop_constraint("ck_eventos_estado", "eventos", type_="check")
    op.create_check_constraint("ck_eventos_estado", "eventos", "estado IN ('borrador', 'publicado')")

    op.drop_column("eventos", "publicado_at")
    op.drop_column("eventos", "version_aplicada")
    op.drop_column("eventos", "version")
    op.drop_index("ix_eventos_organizador_id", table_name="eventos")
    op.drop_column("eventos", "organizador_id")
    op.drop_column("eventos", "descripcion")
    op.drop_index("ix_eventos_tipo", table_name="eventos")
    op.drop_constraint("fk_eventos_tipo", "eventos", type_="foreignkey")
    op.drop_column("eventos", "tipo")

    op.drop_index("ix_evento_participantes_participante_id", table_name="evento_participantes")
    op.drop_table("evento_participantes")
    op.drop_table("participantes")
    op.drop_table("organizadores")
    op.drop_table("tipos_evento")
