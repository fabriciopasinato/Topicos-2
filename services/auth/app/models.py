"""Modelos SQLAlchemy del servicio. Alembic los descubre a traves de Base.metadata."""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ROL_ADMINISTRADOR = "administrador"
ROL_EVENT_OWNER = "event_owner"
ROL_CLIENTE = "cliente"
ROLES = (ROL_ADMINISTRADOR, ROL_EVENT_OWNER, ROL_CLIENTE)

PENDIENTE_VERIFICACION = "pendiente_verificacion"
ACTIVA = "activa"
BLOQUEADA = "bloqueada"
ESTADOS = (PENDIENTE_VERIFICACION, ACTIVA, BLOQUEADA)

MOTIVO_INTENTOS = "intentos_fallidos"
MOTIVO_ADMIN = "restablecimiento_admin"

TOKEN_VERIFICACION = "verificacion"
TOKEN_RESTABLECIMIENTO = "restablecimiento"


class Usuario(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"rol IN {ROLES}", name="ck_users_rol"),
        CheckConstraint(f"estado IN {ESTADOS}", name="ck_users_estado"),
        CheckConstraint(
            f"motivo_bloqueo IS NULL OR motivo_bloqueo IN ('{MOTIVO_INTENTOS}', '{MOTIVO_ADMIN}')",
            name="ck_users_motivo_bloqueo",
        ),
        Index("uq_users_dni", "dni", unique=True, postgresql_where=text("dni IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20))

    # Datos personales y direccion (obligatorios en el registro de clientes;
    # nullables en la base porque el admin semilla y los owners no los tienen).
    nombre: Mapped[str | None] = mapped_column(String(100))
    apellido: Mapped[str | None] = mapped_column(String(100))
    dni: Mapped[str | None] = mapped_column(String(8))
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    telefono: Mapped[str | None] = mapped_column(String(20))
    calle: Mapped[str | None] = mapped_column(String(150))
    numero: Mapped[str | None] = mapped_column(String(10))
    piso_depto: Mapped[str | None] = mapped_column(String(20))
    localidad: Mapped[str | None] = mapped_column(String(100))
    provincia: Mapped[str | None] = mapped_column(String(40))
    codigo_postal: Mapped[str | None] = mapped_column(String(8))

    # Estado y seguridad
    estado: Mapped[str] = mapped_column(String(30), server_default=ACTIVA)
    motivo_bloqueo: Mapped[str | None] = mapped_column(String(30))
    intentos_fallidos: Mapped[int] = mapped_column(Integer, server_default="0")

    # Auditoria (updated_at lo mantiene un trigger de la base)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    """Se guarda solo el hash del refresh token, nunca el valor."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TokenCuenta(Base):
    """Tokens de un solo uso que viajan por email (verificacion, restablecimiento).
    Se guarda solo el hash."""

    __tablename__ = "tokens_cuenta"
    __table_args__ = (
        CheckConstraint(
            f"tipo IN ('{TOKEN_VERIFICACION}', '{TOKEN_RESTABLECIMIENTO}')", name="ck_tokens_cuenta_tipo"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
