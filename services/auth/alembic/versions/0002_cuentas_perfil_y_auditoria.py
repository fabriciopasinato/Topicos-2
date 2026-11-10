"""Cuentas: perfil, direccion, estados, tokens de cuenta y auditoria

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNAS_PERFIL = [
    ("nombre", sa.String(100)),
    ("apellido", sa.String(100)),
    ("dni", sa.String(8)),
    ("fecha_nacimiento", sa.Date()),
    ("telefono", sa.String(20)),
    ("calle", sa.String(150)),
    ("numero", sa.String(10)),
    ("piso_depto", sa.String(20)),
    ("localidad", sa.String(100)),
    ("provincia", sa.String(40)),
    ("codigo_postal", sa.String(8)),
]


def upgrade() -> None:
    # Busqueda sin tildes en el panel de admin. "unaccent" es una extension
    # confiable: la puede crear el duenio de la base sin ser superusuario.
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    for nombre, tipo in COLUMNAS_PERFIL:
        op.add_column("users", sa.Column(nombre, tipo, nullable=True))

    # Las cuentas existentes ya estaban en uso: quedan activas.
    op.add_column("users", sa.Column("estado", sa.String(30), nullable=False, server_default="activa"))
    op.add_column("users", sa.Column("motivo_bloqueo", sa.String(30), nullable=True))
    op.add_column("users", sa.Column("intentos_fallidos", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET updated_at = created_at")
    op.alter_column("users", "updated_at", nullable=False, server_default=sa.func.now())

    op.create_check_constraint(
        "ck_users_estado", "users", "estado IN ('pendiente_verificacion', 'activa', 'bloqueada')"
    )
    op.create_check_constraint(
        "ck_users_motivo_bloqueo",
        "users",
        "motivo_bloqueo IS NULL OR motivo_bloqueo IN ('intentos_fallidos', 'restablecimiento_admin')",
    )
    op.create_index("uq_users_dni", "users", ["dni"], unique=True, postgresql_where=sa.text("dni IS NOT NULL"))

    # updated_at lo mantiene la base ante CUALQUIER UPDATE (tambien los de SQL
    # directo, que el ORM no intercepta).
    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "tokens_cuenta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tipo IN ('verificacion', 'restablecimiento')", name="ck_tokens_cuenta_tipo"),
    )
    op.create_index("ix_tokens_cuenta_user_id", "tokens_cuenta", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_tokens_cuenta_user_id", table_name="tokens_cuenta")
    op.drop_table("tokens_cuenta")
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.drop_index("uq_users_dni", table_name="users")
    op.drop_constraint("ck_users_motivo_bloqueo", "users", type_="check")
    op.drop_constraint("ck_users_estado", "users", type_="check")
    for columna in ("last_login_at", "updated_at", "intentos_fallidos", "motivo_bloqueo", "estado"):
        op.drop_column("users", columna)
    for nombre, _ in reversed(COLUMNAS_PERFIL):
        op.drop_column("users", nombre)
