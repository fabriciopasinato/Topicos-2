"""Validacion local del JWT de acceso y reglas de rutas publicas."""

import re
from dataclasses import dataclass

import jwt

HEADERS_DE_IDENTIDAD = (b"x-user-id", b"x-user-role")


@dataclass(frozen=True)
class Identidad:
    user_id: str
    rol: str
    emitido: int | None = None  # claim iat (epoch en segundos)


class TokenInvalido(Exception):
    pass


def validar_token(token: str, secreto: str) -> Identidad:
    """Verifica firma y expiracion sin consultar a auth."""
    try:
        datos = jwt.decode(token, secreto, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as error:
        raise TokenInvalido(str(error)) from error
    rol = datos.get("rol")
    if not isinstance(rol, str):
        raise TokenInvalido("el token no tiene rol")
    iat = datos.get("iat")
    return Identidad(user_id=str(datos["sub"]), rol=rol, emitido=int(iat) if isinstance(iat, (int, float)) else None)


# Rutas que no requieren token. El resto de /api/* exige un token valido.
RUTAS_PUBLICAS_AUTH = (
    "/api/auth/login",
    "/api/auth/registro",
    "/api/auth/refresh",
    "/api/auth/verificar-email",
    "/api/auth/reenviar-verificacion",
    "/api/auth/olvide-contrasenia",
    "/api/auth/restablecer-contrasenia",
)
_PUBLICAS_EXACTAS = {("POST", ruta) for ruta in RUTAS_PUBLICAS_AUTH}
_DISPONIBILIDAD = re.compile(r"^/api/ventas/eventos/[^/]+/disponibilidad$")


def es_publica(metodo: str, ruta: str) -> bool:
    if metodo == "OPTIONS":  # preflight de CORS
        return True
    if (metodo, ruta) in _PUBLICAS_EXACTAS:
        return True
    if metodo == "GET" and (ruta == "/api/eventos" or ruta.startswith("/api/eventos/")):
        return True
    if metodo == "GET" and _DISPONIBILIDAD.match(ruta):
        return True
    return False
