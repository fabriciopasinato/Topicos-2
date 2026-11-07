"""Validacion local del JWT de acceso y reglas de rutas publicas."""

import re
from dataclasses import dataclass

import jwt

HEADERS_DE_IDENTIDAD = (b"x-user-id", b"x-user-role")


@dataclass(frozen=True)
class Identidad:
    user_id: str
    rol: str


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
    return Identidad(user_id=str(datos["sub"]), rol=rol)


# Rutas que no requieren token. El resto de /api/* exige un token valido.
_PUBLICAS_EXACTAS = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/registro"),
    ("POST", "/api/auth/refresh"),
}
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
