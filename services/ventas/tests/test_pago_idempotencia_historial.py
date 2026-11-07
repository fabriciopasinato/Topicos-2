"""7.7 Pago y cancelacion, 7.8 idempotencia, 7.9 historial."""

import pytest
from sqlalchemy import text

from tests.helpers import CLIENTE, OTRO_CLIENTE, ZONA_GENERAL, asiento, inventario, reservar


@pytest.fixture
def c(client):
    client.post("/internal/inventario", json=inventario())
    return client


def _pagar(c, reserva_id, headers=CLIENTE):
    return c.post(f"/ventas/reservas/{reserva_id}/pago", headers=headers)


def _vencer(db_session):
    db_session.execute(text("UPDATE reservas SET hasta = now() - interval '1 second'"))
    db_session.execute(text("UPDATE tickets SET reservado_hasta = now() - interval '1 second' WHERE estado = 'reservado'"))


# --- 7.7 Pago ---------------------------------------------------------------------

def test_pago_en_termino_crea_la_orden_y_vende(c, db_session):
    reserva = reservar(c, asientos=["A-1", "A-2"]).json()
    r = _pagar(c, reserva["id"])
    assert r.status_code == 201 and r.json()["total"] == 3000.0
    estados = db_session.execute(text("SELECT DISTINCT estado FROM tickets WHERE reserva_id = :r"),
                                 {"r": reserva["id"]}).scalars().all()
    assert estados == ["vendido"]
    assert c.get(f"/ventas/reservas/{reserva['id']}", headers=CLIENTE).json()["estado"] == "pagada"


def test_un_asiento_vendido_no_vuelve_a_liberarse(c, db_session):
    reserva = reservar(c, asientos=["A-1"]).json()
    _pagar(c, reserva["id"])
    _vencer(db_session)  # aunque pase el tiempo, vendido es definitivo
    assert asiento(c, "A-1")["disponible"] is False


def test_pago_de_reserva_vencida_responde_409(c, db_session):
    reserva = reservar(c, asientos=["A-1"]).json()
    _vencer(db_session)
    r = _pagar(c, reserva["id"])
    assert r.status_code == 409
    assert db_session.scalar(text("SELECT count(*) FROM ordenes")) == 0


def test_pago_repetido_devuelve_la_misma_orden(c, db_session):
    reserva = reservar(c, asientos=["A-1"]).json()
    primera = _pagar(c, reserva["id"]).json()
    segunda = _pagar(c, reserva["id"])
    assert segunda.status_code == 201 and segunda.json()["id"] == primera["id"]
    assert db_session.scalar(text("SELECT count(*) FROM ordenes")) == 1


def test_pago_de_reserva_ajena_responde_404(c):
    reserva = reservar(c, asientos=["A-1"]).json()
    assert _pagar(c, reserva["id"], headers=OTRO_CLIENTE).status_code == 404


def test_pago_de_reserva_cancelada_responde_409(c):
    reserva = reservar(c, asientos=["A-1"]).json()
    c.delete(f"/ventas/reservas/{reserva['id']}", headers=CLIENTE)
    assert _pagar(c, reserva["id"]).status_code == 409


# --- 7.7 Cancelacion ----------------------------------------------------------------

def test_cancelacion_libera_al_instante(c):
    reserva = reservar(c, asientos=["A-1"], generales=[(ZONA_GENERAL, 2)]).json()
    assert c.delete(f"/ventas/reservas/{reserva['id']}", headers=CLIENTE).status_code == 204
    assert asiento(c, "A-1")["disponible"] is True
    assert reservar(c, asientos=["A-1"], headers=OTRO_CLIENTE).status_code == 201


def test_cancelar_reserva_pagada_responde_409(c):
    reserva = reservar(c, asientos=["A-1"]).json()
    _pagar(c, reserva["id"])
    assert c.delete(f"/ventas/reservas/{reserva['id']}", headers=CLIENTE).status_code == 409
    assert asiento(c, "A-1")["disponible"] is False


def test_cancelar_reserva_ajena_responde_404(c):
    reserva = reservar(c, asientos=["A-1"]).json()
    assert c.delete(f"/ventas/reservas/{reserva['id']}", headers=OTRO_CLIENTE).status_code == 404


# --- 7.8 Idempotencia ---------------------------------------------------------------

def test_reserva_sin_clave_responde_400(c):
    ticket = asiento(c, "A-1")["ticket_id"]
    r = c.post("/ventas/reservas", json={"evento_id": 1, "asientos": [ticket]}, headers=CLIENTE)
    assert r.status_code == 400
    assert asiento(c, "A-1")["disponible"] is True


def test_reintento_con_la_misma_clave_devuelve_la_misma_reserva(c, db_session):
    primera = reservar(c, asientos=["A-1"], clave="K")
    segunda = reservar(c, asientos=["A-1"], clave="K")
    assert segunda.status_code == 201 and segunda.json()["id"] == primera.json()["id"]
    assert db_session.scalar(text("SELECT count(*) FROM reservas")) == 1


def test_misma_clave_con_otro_contenido_responde_422(c, db_session):
    reservar(c, asientos=["A-1"], clave="K")
    r = reservar(c, asientos=["A-2"], clave="K")
    assert r.status_code == 422
    assert asiento(c, "A-2")["disponible"] is True


def test_misma_clave_de_usuarios_distintos(c):
    a = reservar(c, asientos=["A-1"], clave="K")
    b = reservar(c, asientos=["A-2"], clave="K", headers=OTRO_CLIENTE)
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


def test_reserva_rechazada_se_reevalua_con_la_misma_clave(c):
    otra = reservar(c, asientos=["A-1"], headers=OTRO_CLIENTE).json()
    assert reservar(c, asientos=["A-1"], clave="K").status_code == 409
    c.delete(f"/ventas/reservas/{otra['id']}", headers=OTRO_CLIENTE)
    assert reservar(c, asientos=["A-1"], clave="K").status_code == 201


# --- 7.9 Historial -----------------------------------------------------------------

def test_historial_muestra_solo_ordenes_pagadas_propias(c, db_session):
    pagada = reservar(c, asientos=["A-1", "A-2"]).json()
    _pagar(c, pagada["id"])
    cancelada = reservar(c, asientos=["B-1"]).json()
    c.delete(f"/ventas/reservas/{cancelada['id']}", headers=CLIENTE)
    reservar(c, asientos=["B-2"])  # queda activa, sin pagar
    ajena = reservar(c, asientos=["C-1"], headers=OTRO_CLIENTE).json()
    _pagar(c, ajena["id"], headers=OTRO_CLIENTE)

    compras = c.get("/ventas/compras", headers=CLIENTE).json()
    assert len(compras) == 1
    assert compras[0]["total"] == 3000.0
    assert {(t["fila"], t["numero"]) for t in compras[0]["tickets"]} == {("A", 1), ("A", 2)}
    assert all(t["precio"] == 1500.0 for t in compras[0]["tickets"])


def test_historial_vacio_si_la_reserva_vencio(c, db_session):
    reservar(c, asientos=["A-1"])
    _vencer(db_session)
    assert c.get("/ventas/compras", headers=CLIENTE).json() == []
