"""Tokens de un solo uso que viajan por email (verificacion y restablecimiento).

En la base se guarda solo el hash. Emitir un token nuevo invalida los
anteriores sin usar del mismo usuario y tipo: solo sirve el ultimo.
Consumir es un UPDATE condicional: dos usos simultaneos -> uno solo gana.
"""

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import seguridad


def emitir(session: Session, user_id: int, tipo: str, vigencia: timedelta) -> str:
    session.execute(
        text("UPDATE tokens_cuenta SET used_at = now() WHERE user_id = :u AND tipo = :t AND used_at IS NULL"),
        {"u": user_id, "t": tipo},
    )
    token = seguridad.nuevo_refresh_token()  # mismo generador: aleatorio y opaco
    session.execute(
        text(
            "INSERT INTO tokens_cuenta (user_id, tipo, token_hash, expires_at) "
            "VALUES (:u, :t, :h, now() + make_interval(secs => :s))"
        ),
        {"u": user_id, "t": tipo, "h": seguridad.hash_refresh_token(token), "s": int(vigencia.total_seconds())},
    )
    return token


def vigente(session: Session, token: str, tipo: str) -> int | None:
    """user_id del token si esta vigente (sin consumirlo)."""
    return session.execute(
        text(
            "SELECT user_id FROM tokens_cuenta "
            "WHERE token_hash = :h AND tipo = :t AND used_at IS NULL AND expires_at > now()"
        ),
        {"h": seguridad.hash_refresh_token(token), "t": tipo},
    ).scalar()


def consumir(session: Session, token: str, tipo: str) -> int | None:
    """Marca el token como usado y devuelve su user_id, o None si no es valido."""
    return session.execute(
        text(
            "UPDATE tokens_cuenta SET used_at = now() "
            "WHERE token_hash = :h AND tipo = :t AND used_at IS NULL AND expires_at > now() "
            "RETURNING user_id"
        ),
        {"h": seguridad.hash_refresh_token(token), "t": tipo},
    ).scalar()
