from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class RecintoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    direccion: str = Field(default="", max_length=300)


class RecintoOut(BaseModel):
    id: int
    nombre: str
    direccion: str


class EventoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    fecha: datetime
    recinto_id: int


class EventoPatch(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    fecha: datetime | None = None


class SectorIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


class ZonaIn(BaseModel):
    """Zona numerada: `filas` + `asientos_por_fila`. Zona general: `capacidad`."""

    nombre: str = Field(min_length=1, max_length=100)
    tipo: Literal["numerada", "general"]
    precio: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    capacidad: int | None = Field(default=None, gt=0, le=100_000)
    filas: list[str] | None = None
    asientos_por_fila: int | None = Field(default=None, gt=0, le=500)

    @field_validator("filas")
    @classmethod
    def _filas_validas(cls, filas):
        if filas is None:
            return filas
        limpias = [f.strip() for f in filas]
        if not limpias or any(not f or len(f) > 10 for f in limpias) or len(set(limpias)) != len(limpias):
            raise ValueError("filas debe ser una lista no vacia de identificadores unicos")
        return limpias

    @model_validator(mode="after")
    def _segun_tipo(self):
        if self.tipo == "numerada" and (not self.filas or not self.asientos_por_fila):
            raise ValueError("una zona numerada requiere filas y asientos_por_fila")
        if self.tipo == "general" and not self.capacidad:
            raise ValueError("una zona general requiere capacidad mayor a 0")
        return self


class AsientoOut(BaseModel):
    id: int
    fila: str
    numero: int


class ZonaOut(BaseModel):
    id: int
    nombre: str
    tipo: str
    capacidad: int
    precio: float
    asientos: list[AsientoOut] = []


class SectorOut(BaseModel):
    id: int
    nombre: str
    zonas: list[ZonaOut] = []


class EventoResumen(BaseModel):
    id: int
    nombre: str
    fecha: datetime
    estado: str
    owner_id: int
    recinto: RecintoOut


class EventoDetalle(EventoResumen):
    sectores: list[SectorOut] = []
