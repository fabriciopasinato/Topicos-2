"""Modelos SQLAlchemy del gateway. Alembic los descubre a traves de Base.metadata."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Bitacora(Base):
    """Un registro por cada solicitud HTTP recibida por el gateway."""

    __tablename__ = "bitacora"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    ip: Mapped[str] = mapped_column(String(45))
    metodo: Mapped[str] = mapped_column(String(10))
    ruta: Mapped[str] = mapped_column(String(500))
    user_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[int] = mapped_column(Integer)
    duracion_ms: Mapped[float]
