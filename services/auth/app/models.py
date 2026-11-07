"""Modelos SQLAlchemy del servicio. Alembic los descubre a traves de Base.metadata."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ROL_ADMINISTRADOR = "administrador"
ROL_EVENT_OWNER = "event_owner"
ROL_CLIENTE = "cliente"
ROLES = (ROL_ADMINISTRADOR, ROL_EVENT_OWNER, ROL_CLIENTE)


class Usuario(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"rol IN {ROLES}", name="ck_users_rol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """Se guarda solo el hash del refresh token, nunca el valor."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
