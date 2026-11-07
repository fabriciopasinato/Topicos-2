"""Modelos SQLAlchemy del servicio. Alembic los descubre a traves de Base.metadata.

Eventos DEFINE que se vende (zonas, asientos, precios). Que esta vendido o
reservado lo sabe solo ventas.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

BORRADOR = "borrador"
PUBLICADO = "publicado"
NUMERADA = "numerada"
GENERAL = "general"


class Recinto(Base):
    __tablename__ = "recintos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    direccion: Mapped[str] = mapped_column(String(300), default="")


class Evento(Base):
    __tablename__ = "eventos"
    __table_args__ = (CheckConstraint("estado IN ('borrador', 'publicado')", name="ck_eventos_estado"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recinto_id: Mapped[int] = mapped_column(ForeignKey("recintos.id"))
    estado: Mapped[str] = mapped_column(String(20), default=BORRADOR)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    recinto: Mapped[Recinto] = relationship()
    sectores: Mapped[list["Sector"]] = relationship(
        back_populates="evento", cascade="all, delete-orphan", order_by="Sector.id"
    )


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
