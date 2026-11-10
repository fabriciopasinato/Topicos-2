"""Revocacion de sesiones (design, decision 8).

1. En auth_db: se invalidan todos los refresh tokens del usuario (dentro de
   la transaccion de la operacion).
2. En Redis, despues del commit: revocado:<user_id> = instante (epoch en
   segundos), con TTL igual a la vida del token de acceso. El gateway rechaza
   los tokens de acceso con iat < ese instante.

Contrato con el gateway: auth es el unico que ESCRIBE revocado:*, el gateway
el unico que lo LEE.
"""

import logging
import time
from functools import lru_cache

import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings

log = logging.getLogger("auth.revocacion")

PREFIJO = "revocado:"


def revocar_refresh_tokens(session: Session, user_id: int) -> None:
    session.execute(
        text("UPDATE refresh_tokens SET used_at = now() WHERE user_id = :u AND used_at IS NULL"),
        {"u": user_id},
    )


def publicar(cliente_redis, user_id: int, ttl_segundos: int, instante: int | None = None) -> None:
    """Escribe la marca en Redis. Si Redis no responde, la operacion de negocio
    ya esta hecha (refresh tokens revocados): solo se registra el error."""
    instante = int(time.time()) if instante is None else instante
    try:
        cliente_redis.set(f"{PREFIJO}{user_id}", instante, ex=ttl_segundos)
    except redis.RedisError as error:
        log.error("no se pudo publicar la revocacion del usuario %s en Redis: %s", user_id, error)


@lru_cache
def _cliente() -> redis.Redis:
    return redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)


def get_redis() -> redis.Redis:
    return _cliente()
