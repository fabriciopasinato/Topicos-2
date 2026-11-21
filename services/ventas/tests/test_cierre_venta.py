"""Cierre de la venta de eventos cancelados o iniciados.

Ventas decide solo con sus datos (inventario_eventos): estos tests no levantan
ni simulan el servicio de eventos, lo que tambien cubre el escenario "eventos
caido".
"""

import pytest
from sqlalchemy import text

from tests.helpers import EVENTO, ZONA_GENERAL, disponibilidad, inventario, reservar


@pytest.fixture
def con_inventario(client):
    client.post("/internal/inventario", json={**inventario(), "fecha_inicio": "2099-12-20T21:00:00+00:00"})
    return client


def _cancelar(client, version: int = 2):
    assert client.put(f"/internal/eventos/{EVENTO}", json={"version": version, "cancelado": True}).status_code == 200


def _cantidad(db_session, sql: str) -> int:
    return db_session.scalar(text(sql))


def test_reserva_de_un_evento_cancelado(con_inventario, db_session):
    _cancelar(con_inventario)
    r = reservar(con_inventario, asientos=["A-1"], generales=[(ZONA_GENERAL, 2)])
    assert r.status_code == 409
    assert _cantidad(db_session, "SELECT count(*) FROM reservas") == 0
    assert _cantidad(db_session, "SELECT count(*) FROM tickets WHERE estado <> 'disponible'") == 0


def test_reserva_de_un_evento_iniciado(con_inventario, db_session):
    db_session.execute(text("UPDATE inventario_eventos SET fecha_inicio = now() - interval '10 minutes'"))
    r = reservar(con_inventario, generales=[(ZONA_GENERAL, 1)])
    assert r.status_code == 409
    assert _cantidad(db_session, "SELECT count(*) FROM reservas") == 0


def test_evento_que_empieza_mas_tarde_sigue_a_la_venta(con_inventario, db_session):
    db_session.execute(text("UPDATE inventario_eventos SET fecha_inicio = now() + interval '10 minutes'"))
    assert reservar(con_inventario, generales=[(ZONA_GENERAL, 1)]).status_code == 201


def test_pago_de_una_reserva_de_un_evento_cancelado_despues(con_inventario, db_session):
    reserva = reservar(con_inventario, asientos=["A-1"]).json()
    _cancelar(con_inventario)
    r = con_inventario.post(f"/ventas/reservas/{reserva['id']}/pago", headers={"X-User-Id": "20", "X-User-Role": "cliente"})
    assert r.status_code == 409
    assert _cantidad(db_session, "SELECT count(*) FROM ordenes") == 0
    assert _cantidad(db_session, "SELECT count(*) FROM tickets WHERE estado = 'vendido'") == 0


def test_evento_sin_fecha_registrada_sigue_vendiendo(client):
    client.post("/internal/inventario", json=inventario())  # inventario sin fecha_inicio
    r = reservar(client, generales=[(ZONA_GENERAL, 3)])
    assert r.status_code == 201
    assert disponibilidad(client)[ZONA_GENERAL]["disponibles"] == 7


def test_reintento_tras_el_rechazo_se_evalua_de_nuevo(con_inventario, db_session):
    """El 409 por evento cerrado descarta la Idempotency-Key, como los demas
    rechazos: no queda una clave 'pegada' a un rechazo."""
    _cancelar(con_inventario)
    assert reservar(con_inventario, generales=[(ZONA_GENERAL, 1)], clave="K").status_code == 409
    assert _cantidad(db_session, "SELECT count(*) FROM idempotency_keys") == 0
