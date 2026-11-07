"""Hash de contrasenias y emision de tokens."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()  # argon2id
# Hash de referencia para igualar el tiempo de respuesta cuando el email no existe.
_HASH_FICTICIO = _hasher.hash("contrasenia-ficticia")


def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _HASH_FICTICIO, password) and password_hash is not None
    except VerificationError:
        return False


def emitir_access_token(user_id: int, rol: str, secreto: str, ttl_minutos: int) -> str:
    ahora = datetime.now(timezone.utc)
    datos = {"sub": str(user_id), "rol": rol, "iat": ahora, "exp": ahora + timedelta(minutes=ttl_minutos)}
    return jwt.encode(datos, secreto, algorithm="HS256")


def nuevo_refresh_token() -> str:
    """Valor opaco y aleatorio. En la base solo se guarda su hash."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
