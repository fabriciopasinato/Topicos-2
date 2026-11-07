"""Modelos SQLAlchemy de ventas: la UNICA fuente de verdad de que esta
disponible, reservado o vendido.

Un ticket por entrada, tanto en zonas numeradas (fila + numero) como en zonas
generales (sin fila ni numero). Asi el vencimiento de reservas funciona igual
para todas las zonas.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

DISPONIBLE = "disponible"
RESERVADO = "reservado"
VENDIDO = "vendido"

ACTIVA = "activa"
PAGADA = "pagada"
CANCELADA = "cancelada"


class InventarioEvento(Base):
    """Marca que el inventario de un evento ya fue recibido (idempotencia)."""

    __tablename__ = "inventario_eventos"

    evento_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Reserva(Base):
    __tablename__ = "reservas"
    __table_args__ = (
        CheckConstraint("estado IN ('activa', 'pagada', 'cancelada')", name="ck_reservas_estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    evento_id: Mapped[int] = mapped_column(Integer)
    cantidad: Mapped[int] = mapped_column(Integer)
    # "Vencida" no se guarda: es estado 'activa' con hasta < now().
    hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(20), default=ACTIVA)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Orden(Base):
    __tablename__ = "ordenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    reserva_id: Mapped[int] = mapped_column(ForeignKey("reservas.id"), unique=True)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("estado IN ('disponible', 'reservado', 'vendido')", name="ck_tickets_estado"),
        CheckConstraint("tipo_zona IN ('numerada', 'general')", name="ck_tickets_tipo_zona"),
        # Un asiento numerado existe una sola vez por zona.
        Index(
            "uq_tickets_asiento_numerado", "evento_id", "zona_id", "fila", "numero",
            unique=True, postgresql_where=text("tipo_zona = 'numerada'"),
        ),
        Index("ix_tickets_zona_estado", "zona_id", "estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evento_id: Mapped[int] = mapped_column(Integer, index=True)
    zona_id: Mapped[int] = mapped_column(Integer)
    tipo_zona: Mapped[str] = mapped_column(String(20))
    fila: Mapped[str | None] = mapped_column(String(10))
    numero: Mapped[int | None] = mapped_column(Integer)
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    estado: Mapped[str] = mapped_column(String(20), default=DISPONIBLE)
    reserva_id: Mapped[int | None] = mapped_column(ForeignKey("reservas.id"), index=True)
    reservado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    orden_id: Mapped[int | None] = mapped_column(ForeignKey("ordenes.id"), index=True)


class OrdenItem(Base):
    __tablename__ = "orden_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes.id", ondelete="CASCADE"), index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    reserva_id: Mapped[int | None] = mapped_column(ForeignKey("reservas.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
