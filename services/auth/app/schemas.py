"""Esquemas de entrada y salida de la API de auth."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PROVINCIAS = (
    "Buenos Aires", "Ciudad Autónoma de Buenos Aires", "Catamarca", "Chaco", "Chubut", "Córdoba",
    "Corrientes", "Entre Ríos", "Formosa", "Jujuy", "La Pampa", "La Rioja", "Mendoza", "Misiones",
    "Neuquén", "Río Negro", "Salta", "San Juan", "San Luis", "Santa Cruz", "Santa Fe",
    "Santiago del Estero", "Tierra del Fuego", "Tucumán",
)
Provincia = Literal[PROVINCIAS]  # type: ignore[valid-type]

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
DNI = r"^\d{7,8}$"
TELEFONO = r"^[0-9 +\-]{6,20}$"
CODIGO_POSTAL = r"^(\d{4}|[A-Za-z]\d{4}[A-Za-z]{3})$"


def _edad(nacimiento: date, hoy: date) -> int:
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


class DatosPerfil(BaseModel):
    """Datos personales y direccion editables (sin email, DNI ni rol)."""

    nombre: str = Field(min_length=1, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    fecha_nacimiento: date
    telefono: str = Field(pattern=TELEFONO)
    calle: str = Field(min_length=1, max_length=150)
    numero: str = Field(min_length=1, max_length=10)
    piso_depto: str | None = Field(default=None, max_length=20)
    localidad: str = Field(min_length=1, max_length=100)
    provincia: Provincia
    codigo_postal: str = Field(pattern=CODIGO_POSTAL)

    @field_validator("fecha_nacimiento")
    @classmethod
    def _fecha_valida(cls, valor: date) -> date:
        hoy = date.today()
        if valor >= hoy:
            raise ValueError("la fecha de nacimiento debe ser anterior a hoy")
        if _edad(valor, hoy) > 120:
            raise ValueError("la fecha de nacimiento no es válida")
        return valor


class RegistroIn(DatosPerfil):
    # Cualquier otro campo (por ejemplo "rol") se ignora.
    email: str = Field(pattern=EMAIL, max_length=255)
    password: str = Field(max_length=1000)  # la politica (10-128) la valida el servicio
    dni: str = Field(pattern=DNI)


class PerfilPatch(BaseModel):
    """Edicion parcial del perfil. Email, DNI, rol y estado no existen aca."""

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    apellido: str | None = Field(default=None, min_length=1, max_length=100)
    fecha_nacimiento: date | None = None
    telefono: str | None = Field(default=None, pattern=TELEFONO)
    calle: str | None = Field(default=None, min_length=1, max_length=150)
    numero: str | None = Field(default=None, min_length=1, max_length=10)
    piso_depto: str | None = Field(default=None, max_length=20)
    localidad: str | None = Field(default=None, min_length=1, max_length=100)
    provincia: Provincia | None = None
    codigo_postal: str | None = Field(default=None, pattern=CODIGO_POSTAL)

    @field_validator("fecha_nacimiento")
    @classmethod
    def _fecha_valida(cls, valor: date | None) -> date | None:
        return valor if valor is None else DatosPerfil._fecha_valida(valor)


class EventOwnerIn(BaseModel):
    email: str = Field(pattern=EMAIL, max_length=255)
    password: str = Field(max_length=1000)


class LoginIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class EmailIn(BaseModel):
    email: str = Field(max_length=255)


class RestablecerIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    contrasenia: str = Field(max_length=1000)


class CambioContraseniaIn(BaseModel):
    actual: str = Field(max_length=1000)
    nueva: str = Field(max_length=1000)


class UsuarioOut(BaseModel):
    id: int
    email: str
    rol: str


class PerfilOut(BaseModel):
    id: int
    email: str
    rol: str
    estado: str
    nombre: str | None
    apellido: str | None
    dni: str | None
    fecha_nacimiento: date | None
    telefono: str | None
    calle: str | None
    numero: str | None
    piso_depto: str | None
    localidad: str | None
    provincia: str | None
    codigo_postal: str | None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class CuentaAdminOut(PerfilOut):
    motivo_bloqueo: str | None
    intentos_fallidos: int


class PaginaCuentas(BaseModel):
    items: list[CuentaAdminOut]
    total: int
    pagina: int
    tamanio: int


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
