"""Tests de concurrencia de ventas (7.4, 7.5, 7.7, 7.8).

Cada participante es un hilo con su propia conexion a PostgreSQL y commits
reales; una barrera los larga a todos juntos. No usan el rollback por test:
la fixture `db_concurrente` limpia las tablas al terminar.
"""

import threading
import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import servicio
from tests.conftest import TEST_DATABASE_URL
from tests.helpers import EVENTO, ZONA_GENERAL, inventario

pytestmark = pytest.mark.concurrencia

TTL, MAXIMO = 5, 10


@pytest.fixture
def engine_paralelo(db_concurrente):
    """Pool grande para que 20 hilos tengan conexion a la vez."""
    eng = create_engine(TEST_DATABASE_URL, pool_size=25, max_overflow=0)
    with Session(eng) as s:
        servicio.recibir_inventario(s, inventario(capacidad_general=5))
    yield eng
    eng.dispose()


def _ticket(eng, fila: str, numero: int) -> int:
    with eng.connect() as c:
        return c.scalar(text("SELECT id FROM tickets WHERE fila = :f AND numero = :n"), {"f": fila, "n": numero})


def _en_paralelo(eng, tareas):
    """Ejecuta cada tarea(session) en su hilo, todas a la vez. Devuelve los
    resultados ('ok'/nombre de la excepcion) en el orden de las tareas."""
    barrera = threading.Barrier(len(tareas))
    resultados = [None] * len(tareas)

    def correr(i, tarea):
        with Session(eng) as session:
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


def _pedido(asientos=(), generales=()):
    return servicio.PedidoReserva(evento_id=EVENTO, asientos=tuple(asientos), generales=tuple(generales))


def _reservar(user_id, pedido, clave=None):
    clave = clave or f"clave-{user_id}-{time.monotonic_ns()}"
    return lambda s: servicio.reservar(s, user_id, clave, pedido, TTL, MAXIMO).id


def test_dos_reservas_del_mismo_asiento_un_201_y_un_409(engine_paralelo):
    b7 = _ticket(engine_paralelo, "B", 7)
    resultados = _en_paralelo(engine_paralelo, [_reservar(1, _pedido([b7])), _reservar(2, _pedido([b7]))])
    assert sorted(r[0] for r in resultados) == ["NoDisponible", "ok"]
    with engine_paralelo.connect() as c:
        assert c.scalar(text("SELECT count(DISTINCT reserva_id) FROM tickets WHERE id = :t"), {"t": b7}) == 1


def test_reservas_cruzadas_sin_deadlock(engine_paralelo):
    a1, a2 = _ticket(engine_paralelo, "A", 1), _ticket(engine_paralelo, "A", 2)
    inicio = time.monotonic()
    resultados = _en_paralelo(engine_paralelo, [
        _reservar(1, _pedido([a1, a2])),
        _reservar(2, _pedido([a2, a1])),
    ])
    assert sorted(r[0] for r in resultados) == ["NoDisponible", "ok"]
    assert time.monotonic() - inicio < 5  # ni deadlock ni espera indefinida


def test_20_reservas_por_5_entradas_generales(engine_paralelo):
    tareas = [_reservar(100 + i, _pedido(generales=[(ZONA_GENERAL, 1)])) for i in range(20)]
    resultados = _en_paralelo(engine_paralelo, tareas)
    exitos = [r for r in resultados if r[0] == "ok"]
    assert len(exitos) == 5
    assert sum(1 for r in resultados if r[0] == "NoDisponible") == 15
    with engine_paralelo.connect() as c:
        # cada ticket general quedo en a lo sumo una reserva, y ninguno sobra
        reservados = c.scalar(text("SELECT count(*) FROM tickets WHERE tipo_zona = 'general' AND estado = 'reservado'"))
        distintos = c.scalar(text("SELECT count(DISTINCT reserva_id) FROM tickets WHERE tipo_zona = 'general'"))
    assert reservados == 5 and distintos == 5


def test_misma_clave_simultanea_crea_una_sola_reserva(engine_paralelo):
    a3 = _ticket(engine_paralelo, "A", 3)
    pedido = _pedido([a3])
    resultados = _en_paralelo(engine_paralelo, [_reservar(7, pedido, "K"), _reservar(7, pedido, "K")])
    assert [r[0] for r in resultados] == ["ok", "ok"]
    assert resultados[0][1] == resultados[1][1]
    with engine_paralelo.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM reservas")) == 1


def test_pago_contra_nueva_reserva_en_el_momento_del_vencimiento(engine_paralelo):
    """Se repite con distintos desfasajes alrededor del vencimiento. En todos
    los casos gana exactamente uno y el asiento nunca queda vendido a uno y
    reservado por otro."""
    for intento in range(8):
        with engine_paralelo.begin() as c:
            # Reset sin TRUNCATE ... CASCADE (que vaciaria tambien tickets por la FK).
            c.execute(text("UPDATE tickets SET estado = 'disponible', reserva_id = NULL, "
                           "reservado_hasta = NULL, orden_id = NULL"))
            for tabla in ("orden_items", "idempotency_keys", "ordenes", "reservas"):
                c.execute(text(f"DELETE FROM {tabla}"))
        b2 = _ticket(engine_paralelo, "B", 2)
        with Session(engine_paralelo) as s:
            reserva_id = servicio.reservar(s, 1, f"k-{intento}", _pedido([b2]), TTL, MAXIMO).id
        # La reserva vence ~40 ms despues de que arrancan los hilos.
        with engine_paralelo.begin() as c:
            c.execute(text("UPDATE reservas SET hasta = clock_timestamp() + interval '40 milliseconds'"))
            c.execute(text("UPDATE tickets SET reservado_hasta = clock_timestamp() + interval '40 milliseconds' "
                           "WHERE reserva_id = :r"), {"r": reserva_id})

        demora = intento * 0.01  # 0 a 70 ms: antes, durante y despues del vencimiento

        def pagar(s):
            time.sleep(demora)
            return servicio.pagar(s, reserva_id, 1).id

        def nueva_reserva(s):
            time.sleep(0.04)
            return servicio.reservar(s, 2, f"k2-{intento}", _pedido([b2]), TTL, MAXIMO).id

        resultados = _en_paralelo(engine_paralelo, [pagar, nueva_reserva])
        ganadores = [r for r in resultados if r[0] == "ok"]
        assert len(ganadores) == 1, (intento, resultados)

        with engine_paralelo.connect() as c:
            estado, reserva_actual, orden = c.execute(
                text("SELECT estado, reserva_id, orden_id FROM tickets WHERE id = :t"), {"t": b2}).one()
        if resultados[0][0] == "ok":  # gano el pago
            assert estado == "vendido" and orden is not None and reserva_actual == reserva_id
        else:  # gano la nueva reserva
            assert estado == "reservado" and orden is None and reserva_actual != reserva_id


def test_dos_pagos_simultaneos_crean_una_sola_orden(engine_paralelo):
    a4 = _ticket(engine_paralelo, "A", 4)
    with Session(engine_paralelo) as s:
        reserva_id = servicio.reservar(s, 1, "k-pago", _pedido([a4]), TTL, MAXIMO).id
    resultados = _en_paralelo(engine_paralelo, [
        lambda s: servicio.pagar(s, reserva_id, 1).id,
        lambda s: servicio.pagar(s, reserva_id, 1).id,
    ])
    assert [r[0] for r in resultados] == ["ok", "ok"]
    assert resultados[0][1] == resultados[1][1]
    with engine_paralelo.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM ordenes")) == 1
