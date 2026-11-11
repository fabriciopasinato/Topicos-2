"""Verificacion de sesiones revocadas.

Contrato con auth: auth ESCRIBE revocado:<user_id> = instante de revocacion
(epoch en segundos) cuando bloquea una cuenta o cambia/restablece su
contrasenia. El gateway LEE esa marca y rechaza los tokens de acceso emitidos
ANTES (iat < marca). Un token emitido en el mismo segundo se acepta, para que
el par nuevo que entrega el cambio de contrasenia siga sirviendo.

Si Redis no responde se deja pasar (fail-open), igual que el rate limit.
"""

import sys

from app.seguridad import Identidad

PREFIJO = "revocado:"


async def esta_revocado(redis, identidad: Identidad) -> bool:
    try:
        marca = await redis.get(f"{PREFIJO}{identidad.user_id}")
    except Exception as error:  # noqa: BLE001
        print(f"WARNING revocacion sin Redis ({type(error).__name__}): se deja pasar", file=sys.stdout, flush=True)
        return False
    if marca is None:
        return False
    if identidad.emitido is None:
        return True  # sin iat no se puede saber si es anterior: se rechaza
    return identidad.emitido < int(marca)
