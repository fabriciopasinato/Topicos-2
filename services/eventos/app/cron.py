"""eventos-cron: reintenta las operaciones pendientes hacia ventas.

    python -m app.cron           # bucle
    python -m app.cron --salud   # healthcheck
"""

import logging
import sys
import time
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import servicio
from app.cliente_ventas import ClienteVentas, InventarioInexistente, VentasNoDisponible, get_cliente_ventas
from app.config import get_settings
from app.db import get_engine
from app.models import EstadoOperacion, OperacionVentas

log = logging.getLogger("eventos-cron")


class Intento(StrEnum):
    NINGUNA = "ninguna"
    CONFIRMADA = "confirmada"
    POSTERGADA = "postergada"  # ventas respondio, pero no pudo aplicarla (404)
    VENTAS_NO_RESPONDE = "ventas_no_responde"


def procesar_una(session: Session, ventas: ClienteVentas) -> Intento:
    op = session.scalar(
        select(OperacionVentas)
        .where(OperacionVentas.estado == EstadoOperacion.PENDIENTE, OperacionVentas.proximo_intento_at <= func.now())
        .order_by(OperacionVentas.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if op is None:
        session.rollback()
        return Intento.NINGUNA

    op_id, evento_id, tipo, version, intento = op.id, op.evento_id, op.tipo, op.version, op.intentos + 1
    cambios = servicio.EFECTOS[op.tipo].cambios_para_ventas(op)
    try:
        # Con el lock tomado: otra instancia del cron no puede enviar la misma operacion.
        ventas.actualizar_evento(evento_id, version, **cambios)
    except VentasNoDisponible as error:
        log.warning("operacion %s (evento %s, %s v%s) sin confirmar, intento %s: %s",
                    op_id, evento_id, tipo, version, intento, error)
        servicio.registrar_fallo(session, op_id, error)
        return Intento.POSTERGADA if isinstance(error, InventarioInexistente) else Intento.VENTAS_NO_RESPONDE
    servicio.aplicar(session, op_id)
    log.info("operacion %s (evento %s, %s v%s) confirmada en el intento %s", op_id, evento_id, tipo, version, intento)
    return Intento.CONFIRMADA


def ciclo(nueva_sesion: Callable[[], Session], ventas: ClienteVentas, lote: int) -> int:
    procesadas = 0
    while procesadas < lote:
        with nueva_sesion() as session:
            intento = procesar_una(session, ventas)
        if intento == Intento.NINGUNA:
            break
        procesadas += 1
        if intento == Intento.VENTAS_NO_RESPONDE:
            break  # las demas fallarian igual (y con ventas colgado, cada una esperaria el timeout)
    return procesadas


def latir(ruta: str) -> None:
    Path(ruta).touch()


def esta_sano(ruta: str, intervalo: float, ahora: float | None = None) -> bool:
    try:
        antiguedad = (time.time() if ahora is None else ahora) - Path(ruta).stat().st_mtime
    except FileNotFoundError:
        return False
    return antiguedad < 3 * intervalo


def main() -> None:
    settings = get_settings()
    if "--salud" in sys.argv:
        sys.exit(0 if esta_sano(settings.cron_latido, settings.cron_intervalo_segundos) else 1)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ventas = get_cliente_ventas()
    log.info("iniciado: un ciclo cada %ss, hasta %s operaciones por ciclo",
             settings.cron_intervalo_segundos, settings.cron_lote)
    while True:
        try:
            ciclo(lambda: Session(get_engine()), ventas, settings.cron_lote)
            latir(settings.cron_latido)
        except Exception:  # noqa: BLE001 - la base caida no debe matar el proceso
            log.exception("ciclo fallido; se reintenta en el proximo")
        time.sleep(settings.cron_intervalo_segundos)


if __name__ == "__main__":
    main()
