"""Concurrencia del ciclo de vida: reprogramacion y cancelacion simultaneas."""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import servicio
from app.identidad import Identidad
from app.schemas import EventoIn
from tests.helpers import VentasFalsa

pytestmark = pytest.mark.concurrencia

OWNER = Identidad(user_id=10, rol="event_owner")


@pytest.fixture
def evento_publicado(db_concurrente):
    """Evento publicado con commits reales; ventas falsa ya tiene su inventario."""
    ventas = VentasFalsa()
    with Session(db_concurrente) as s:
        recinto = servicio.crear_recinto(s, "Estadio", "")
        evento = servicio.crear_evento(s, EventoIn(
            nombre="Recital", fecha=datetime.now(UTC) + timedelta(days=30), recinto_id=recinto.id,
            tipo="recital", organizador="DF",
        ), OWNER)
        s.execute(text("UPDATE eventos SET estado = 'publicado', publicado_at = now() WHERE id = :e"), {"e": evento.id})
        s.commit()
        evento_id = evento.id
    ventas.eventos[evento_id] = {"version": 0, "fecha_inicio": None, "cancelado": False}
    return evento_id, ventas


def _en_paralelo(engine, tareas):
    barrera = threading.Barrier(len(tareas))
    resultados = [None] * len(tareas)

    def correr(i, tarea):
        with Session(engine) as session:
            barrera.wait()
            try:
                resultados[i] = ("ok", tarea(session))
            except Exception as error:  # noqa: BLE001
                resultados[i] = (type(error).__name__, None)

    hilos = [threading.Thread(target=correr, args=(i, t)) for i, t in enumerate(tareas)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    assert not any(h.is_alive() for h in hilos), "algun hilo quedo bloqueado"
    return resultados


@pytest.mark.parametrize("ventas_caida", [False, True])
def test_reprogramacion_y_cancelacion_simultaneas_terminan_canceladas(db_concurrente, evento_publicado, ventas_caida):
    evento_id, ventas = evento_publicado
    ventas.caida = ventas_caida
    nueva = datetime.now(UTC) + timedelta(days=60)

    resultados = _en_paralelo(db_concurrente, [
        lambda s: servicio.reprogramar(s, evento_id, OWNER, ventas, nueva),
        lambda s: servicio.cancelar(s, evento_id, OWNER, ventas),
    ])

    # La cancelacion siempre se registra. La reprogramacion se registra si
    # llego primero, o recibe 409 si vio la cancelacion (pendiente o aplicada).
    assert resultados[1][0] == "ok"
    assert resultados[0][0] in {"ok", "Conflicto"}

    with db_concurrente.connect() as c:
        versiones = c.execute(text(
            "SELECT version FROM operaciones_ventas WHERE evento_id = :e ORDER BY version"), {"e": evento_id}
        ).scalars().all()
    assert len(versiones) == len(set(versiones))  # nunca dos operaciones con la misma version

    if ventas_caida:  # ventas vuelve: se reenvia todo lo pendiente, en cualquier orden
        ventas.caida = False
        with Session(db_concurrente) as s:
            pendientes = [op.id for op in servicio.operaciones_pendientes(s, evento_id)]
        for op_id in reversed(pendientes):  # a proposito, en orden inverso
            with Session(db_concurrente) as s:
                assert servicio.enviar(s, op_id, ventas) == servicio.Resultado.APLICADO

    with db_concurrente.connect() as c:
        assert c.scalar(text("SELECT estado FROM eventos WHERE id = :e"), {"e": evento_id}) == "cancelado"
    assert ventas.eventos[evento_id]["cancelado"] is True
