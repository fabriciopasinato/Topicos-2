"""Modelos SQLAlchemy del servicio. Alembic los descubre a traves de Base.metadata.

Eventos DEFINE que se vende (zonas, asientos, precios). Que esta vendido o
reservado lo sabe solo ventas.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Column, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Table, Text, UniqueConstraint,
    func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# "finalizado" no se guarda: se calcula (publicado cuya fecha ya llego).
BORRADOR = "borrador"
PUBLICADO = "publicado"
CANCELADO = "cancelado"
FINALIZADO = "finalizado"
NUMERADA = "numerada"
GENERAL = "general"


class TipoEvento(Base):
    __tablename__ = "tipos_evento"

    codigo: Mapped[str] = mapped_column(String(30), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))


class Organizador(Base):
    """Quien produce el evento; no es el owner (la cuenta que lo carga)."""

    __tablename__ = "organizadores"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    clave: Mapped[str] = mapped_column(String(200), unique=True)  # nombre normalizado


class Participante(Base):
    __tablename__ = "participantes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    clave: Mapped[str] = mapped_column(String(200), unique=True)  # nombre normalizado


evento_participantes = Table(
    "evento_participantes",
    Base.metadata,
    Column("evento_id", ForeignKey("eventos.id", ondelete="CASCADE"), primary_key=True),
    Column("participante_id", ForeignKey("participantes.id"), primary_key=True, index=True),
)


class Recinto(Base):
    __tablename__ = "recintos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    direccion: Mapped[str] = mapped_column(String(300), default="")


class Evento(Base):
    __tablename__ = "eventos"
    __table_args__ = (
        CheckConstraint("estado IN ('borrador', 'publicado', 'cancelado')", name="ck_eventos_estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recinto_id: Mapped[int] = mapped_column(ForeignKey("recintos.id"))
    estado: Mapped[str] = mapped_column(String(20), default=BORRADOR)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tipo: Mapped[str] = mapped_column(ForeignKey("tipos_evento.codigo", name="fk_eventos_tipo"), index=True)
    descripcion: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Nullable solo por eventos anteriores a este dato: la API lo exige.
    organizador_id: Mapped[int | None] = mapped_column(ForeignKey("organizadores.id"), index=True)
    # version: ultima asignada; version_aplicada: ultima confirmada por ventas.
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    version_aplicada: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    publicado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recinto: Mapped[Recinto] = relationship()
    organizador: Mapped[Organizador | None] = relationship()
    participantes: Mapped[list[Participante]] = relationship(
        secondary=evento_participantes, order_by="Participante.nombre"
    )
    sectores: Mapped[list["Sector"]] = relationship(
        back_populates="evento", cascade="all, delete-orphan", order_by="Sector.id"
    )


class TipoOperacion(StrEnum):
    """Enum y no tabla: un tipo nuevo exige programar su efecto (servicio.EFECTOS)."""

    REPROGRAMAR = "reprogramar"
    CANCELAR = "cancelar"


class EstadoOperacion(StrEnum):
    PENDIENTE = "pendiente"
    CONFIRMADA = "confirmada"


def _valores_sql(enum: type[StrEnum]) -> str:
    return ", ".join(f"'{v.value}'" for v in enum)


class OperacionVentas(Base):
    """Outbox: se guarda antes de avisar a ventas, para poder reintentar."""

    __tablename__ = "operaciones_ventas"
    __table_args__ = (
        CheckConstraint(f"tipo IN ({_valores_sql(TipoOperacion)})", name="ck_operaciones_ventas_tipo"),
        CheckConstraint(f"estado IN ({_valores_sql(EstadoOperacion)})", name="ck_operaciones_ventas_estado"),
        CheckConstraint(
            f"tipo <> '{TipoOperacion.REPROGRAMAR}' OR fecha IS NOT NULL", name="ck_operaciones_ventas_fecha"
        ),
        UniqueConstraint("evento_id", "version", name="uq_operaciones_ventas_evento_version"),
        Index("ix_operaciones_ventas_pendientes", "proximo_intento_at", postgresql_where=text("estado = 'pendiente'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evento_id: Mapped[int] = mapped_column(ForeignKey("eventos.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(
        String(20), default=EstadoOperacion.PENDIENTE, server_default=EstadoOperacion.PENDIENTE.value
    )
    intentos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    proximo_intento_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Sector(Base):
    __tablename__ = "sectores"

    id: Mapped[int] = mapped_column(primary_key=True)
    evento_id: Mapped[int] = mapped_column(ForeignKey("eventos.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(100))

    evento: Mapped[Evento] = relationship(back_populates="sectores")
    zonas: Mapped[list["Zona"]] = relationship(
        back_populates="sector", cascade="all, delete-orphan", order_by="Zona.id"
    )


class Zona(Base):
    __tablename__ = "zonas"
    __table_args__ = (
        CheckConstraint("tipo IN ('numerada', 'general')", name="ck_zonas_tipo"),
        CheckConstraint("capacidad > 0", name="ck_zonas_capacidad"),
        CheckConstraint("precio >= 0", name="ck_zonas_precio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectores.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    tipo: Mapped[str] = mapped_column(String(20))
    capacidad: Mapped[int] = mapped_column(Integer)
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    sector: Mapped[Sector] = relationship(back_populates="zonas")
    asientos: Mapped[list["Asiento"]] = relationship(
        back_populates="zona", cascade="all, delete-orphan", order_by="Asiento.id"
    )


class Asiento(Base):
    __tablename__ = "asientos"
    __table_args__ = (UniqueConstraint("zona_id", "fila", "numero", name="uq_asientos_zona_fila_numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    zona_id: Mapped[int] = mapped_column(ForeignKey("zonas.id", ondelete="CASCADE"), index=True)
    fila: Mapped[str] = mapped_column(String(10))
    numero: Mapped[int] = mapped_column(Integer)

    zona: Mapped[Zona] = relationship(back_populates="asientos")
