"""Registro de cada solicitud en gateway_db.

Se escribe ANTES de devolver la respuesta, con un tiempo maximo acotado.
Si la base no responde, el registro sale por stdout (JSON) y la respuesta se
devuelve igual: la bitacora nunca bloquea el servicio (fail-open).
"""

import asyncio
import json
import sys
from datetime import datetime, timezone

from sqlalchemy import insert, text

from app.models import Bitacora


async def registrar(engine, registro: dict, timeout_segundos: float) -> None:
    try:
        await asyncio.wait_for(_insertar(engine, registro, timeout_segundos), timeout_segundos)
    except Exception as error:  # noqa: BLE001 - cualquier falla cae a stdout
        salida = {
            "evento": "bitacora_no_persistida",
            "error": type(error).__name__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **registro,
        }
        print(json.dumps(salida), file=sys.stdout, flush=True)


async def _insertar(engine, registro: dict, timeout_segundos: float) -> None:
    async with engine.begin() as conexion:
        ms = max(1, int(timeout_segundos * 1000))
        await conexion.execute(text(f"SET LOCAL statement_timeout = {ms}"))
        await conexion.execute(insert(Bitacora).values(**registro))
