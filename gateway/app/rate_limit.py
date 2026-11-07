"""Rate limit por IP con ventana fija de 60 s en Redis.

Clave: rate_limit:<grupo>:<ip>:<ventana>, donde <ventana> es el minuto actual.
Los contadores viven en Redis, asi todas las instancias del gateway comparten
el mismo conteo por IP.
"""

import math
import time

from app.config import Settings

VENTANA_SEGUNDOS = 60

_RUTAS_AUTH = {"/api/auth/login", "/api/auth/registro", "/api/auth/refresh"}


def grupo_de(metodo: str, ruta: str) -> str:
    if metodo == "POST" and ruta in _RUTAS_AUTH:
        return "auth"
    if metodo in ("POST", "DELETE") and ruta.startswith("/api/ventas/reservas"):
        return "compra"  # reservar, pagar y cancelar
    return "general"


def limite_de(grupo: str, settings: Settings) -> int:
    return {
        "auth": settings.rate_limit_auth,
        "compra": settings.rate_limit_compra,
        "general": settings.rate_limit_general,
    }[grupo]


async def consumir(redis, grupo: str, ip: str, limite: int, ahora: float | None = None) -> int | None:
    """Cuenta la solicitud. Devuelve los segundos de Retry-After si se supero
    el limite, o None si la solicitud puede seguir."""
    ahora = time.time() if ahora is None else ahora
    ventana = int(ahora // VENTANA_SEGUNDOS)
    fin_de_ventana = (ventana + 1) * VENTANA_SEGUNDOS
    clave = f"rate_limit:{grupo}:{ip}:{ventana}"

    pipe = redis.pipeline()
    pipe.incr(clave)
    pipe.expireat(clave, fin_de_ventana)
    cantidad, _ = await pipe.execute()

    if cantidad > limite:
        return max(1, math.ceil(fin_de_ventana - ahora))
    return None
