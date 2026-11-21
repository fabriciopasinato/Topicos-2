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


class TipoEventoOut(BaseModel):
    codigo: str
    nombre: str


class OrganizadorOut(BaseModel):
    id: int
    nombre: str


class ParticipanteOut(BaseModel):
    id: int
    nombre: str


class EventoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    fecha: datetime
    recinto_id: int
    tipo: str = Field(min_length=1, max_length=30)  # codigo del catalogo de tipos
    organizador: str = Field(max_length=200)  # nombre: se busca o se crea
    participantes: list[str] = Field(default=[], max_length=50)  # nombres: se buscan o se crean
    descripcion: str = Field(default="", max_length=5000)


class EventoPatch(BaseModel):
    """Edicion de datos descriptivos. La fecha NO se edita aca: se cambia con
    la reprogramacion, que avisa a ventas. Los campos ausentes no cambian;
    `participantes` reemplaza la lista completa."""

    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = Field(default=None, max_length=5000)
    tipo: str | None = Field(default=None, min_length=1, max_length=30)
    organizador: str | None = Field(default=None, max_length=200)
    participantes: list[str] | None = Field(default=None, max_length=50)
    recinto_id: int | None = None  # solo en borrador

    @model_validator(mode="before")
    @classmethod
    def _sin_fecha(cls, datos):
        if isinstance(datos, dict) and "fecha" in datos:
            raise ValueError("la fecha no se edita: se cambia con POST /eventos/{id}/reprogramar")
        return datos


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
    estado: str  # borrador | publicado | cancelado | finalizado (calculado)
    owner_id: int
    recinto: RecintoOut
    tipo: str
    organizador: OrganizadorOut | None  # None solo en eventos anteriores a este dato
    participantes: list[ParticipanteOut] = []


class EventoDetalle(EventoResumen):
    descripcion: str = ""
    sectores: list[SectorOut] = []
