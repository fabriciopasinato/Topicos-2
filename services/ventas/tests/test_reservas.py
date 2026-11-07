"""7.4 Reserva de numerados, 7.5 generales, 7.6 vencimiento."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.main import app
from tests.helpers import (
    CLIENTE, OTRO_CLIENTE, OWNER, ZONA_GENERAL, asiento, disponibilidad, inventario, reservar,
)


@pytest.fixture
def c(client):
    client.post("/internal/inventario", json=inventario())
    return client


# --- 7.4 Numerados ----------------------------------------------------------

def test_reserva_de_dos_asientos(c):
    r = reservar(c, asientos=["A-1", "A-2"])
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["estado"] == "activa" and cuerpo["hasta"]
    assert {(t["fila"], t["numero"]) for t in cuerpo["tickets"]} == {("A", 1), ("A", 2)}
    assert cuerpo["total"] == 3000.0
    assert not asiento(c, "A-1")["disponible"] and not asiento(c, "A-2")["disponible"]


def test_un_asiento_no_disponible_rechaza_toda_la_reserva(c):
    reservar(c, asientos=["A-2"], headers=OTRO_CLIENTE)
    r = reservar(c, asientos=["A-1", "A-2"])
    assert r.status_code == 409
    assert "A-2" in r.json()["detail"]
    assert asiento(c, "A-1")["disponible"] is True


def test_asiento_vendido_no_se_puede_reservar(c, db_session):
    db_session.execute(text("UPDATE tickets SET estado = 'vendido' WHERE fila = 'B' AND numero = 1"))
    assert reservar(c, asientos=["B-1"]).status_code == 409


def test_supera_el_maximo_de_tickets(c):
    nombres = [f"A-{n}" for n in range(1, 11)] + ["B-1"]
    r = reservar(c, asientos=nombres)
    assert r.status_code == 422
    assert all(asiento(c, n)["disponible"] for n in nombres)


def test_reserva_vacia_responde_422(c):
    assert reservar(c).status_code == 422


def test_solo_clientes_pueden_reservar(c):
    assert reservar(c, asientos=["A-1"], headers=OWNER).status_code == 403
    r = c.post("/ventas/reservas", json={"evento_id": 1, "asientos": []}, headers={"Idempotency-Key": "k"})
    assert r.status_code == 401


def test_asiento_de_otro_evento_no_se_reserva(c):
    c.post("/internal/inventario", json=inventario(evento_id=2))
    ticket_evento_2 = asiento(c, "A-1", evento_id=2)["ticket_id"]
    r = c.post("/ventas/reservas", json={"evento_id": 1, "asientos": [ticket_evento_2]},
               headers={**CLIENTE, "Idempotency-Key": "k-otro-evento"})
    assert r.status_code == 409


# --- 7.5 Generales ------------------------------------------------------------

def test_reserva_general_con_disponibles_suficientes(c):
    r = reservar(c, generales=[(ZONA_GENERAL, 3)])
    assert r.status_code == 201 and len(r.json()["tickets"]) == 3
    assert disponibilidad(c)[ZONA_GENERAL]["disponibles"] == 7


def test_reserva_general_insuficiente_responde_409_y_no_toca_nada(c):
    reservar(c, generales=[(ZONA_GENERAL, 7)], headers=OTRO_CLIENTE)
    r = reservar(c, generales=[(ZONA_GENERAL, 5)])
    assert r.status_code == 409
    assert disponibilidad(c)[ZONA_GENERAL]["disponibles"] == 3


def test_reserva_mixta_numerados_y_generales(c):
    r = reservar(c, asientos=["C-3"], generales=[(ZONA_GENERAL, 2)])
    assert r.status_code == 201 and len(r.json()["tickets"]) == 3
    assert r.json()["total"] == 1500.0 + 2 * 800.0


# --- 7.6 Vencimiento ------------------------------------------------------------

def _vencer_todo(db_session):
    db_session.execute(text("UPDATE reservas SET hasta = now() - interval '1 second'"))
    db_session.execute(text(
        "UPDATE tickets SET reservado_hasta = now() - interval '1 second' WHERE estado = 'reservado'"
    ))


def test_reserva_vencida_libera_el_asiento_y_otro_puede_reservarlo(c, db_session):
    reservar(c, asientos=["C-3"])
    _vencer_todo(db_session)
    assert asiento(c, "C-3")["disponible"] is True
    r = reservar(c, asientos=["C-3"], headers=OTRO_CLIENTE)
    assert r.status_code == 201


def test_reserva_vencida_de_zona_general_libera_las_entradas(c, db_session):
    reservar(c, generales=[(ZONA_GENERAL, 10)])
    assert disponibilidad(c)[ZONA_GENERAL]["disponibles"] == 0
    _vencer_todo(db_session)
    assert disponibilidad(c)[ZONA_GENERAL]["disponibles"] == 10
    assert reservar(c, generales=[(ZONA_GENERAL, 10)], headers=OTRO_CLIENTE).status_code == 201


def test_reserva_de_hace_2_minutos_sigue_bloqueando(c, db_session):
    reservar(c, asientos=["C-3"])
    db_session.execute(text("UPDATE reservas SET hasta = hasta - interval '2 minutes'"))
    db_session.execute(text("UPDATE tickets SET reservado_hasta = reservado_hasta - interval '2 minutes' "
                            "WHERE estado = 'reservado'"))
    assert reservar(c, asientos=["C-3"], headers=OTRO_CLIENTE).status_code == 409


def test_la_reserva_vencida_se_informa_como_vencida(c, db_session):
    reserva = reservar(c, asientos=["C-3"]).json()
    _vencer_todo(db_session)
    assert c.get(f"/ventas/reservas/{reserva['id']}", headers=CLIENTE).json()["estado"] == "vencida"


def test_duracion_por_defecto_es_5_minutos(c, db_session):
    reserva = reservar(c, asientos=["C-3"]).json()
    minutos = db_session.scalar(text(
        "SELECT extract(epoch FROM hasta - created_at) / 60 FROM reservas WHERE id = :r"), {"r": reserva["id"]})
    assert 4.9 < float(minutos) <= 5.0


def test_duracion_configurada_en_10_minutos(c, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "reserva_ttl_minutes", 10)
    reserva = reservar(c, asientos=["C-3"]).json()
    minutos = db_session.scalar(text(
        "SELECT extract(epoch FROM hasta - created_at) / 60 FROM reservas WHERE id = :r"), {"r": reserva["id"]})
    assert 9.9 < float(minutos) <= 10.0


def test_las_reservas_se_liberan_aunque_ventas_se_reinicie(c, db_session):
    reservar(c, asientos=["C-3"])
    # "Reinicio": una instancia nueva de la app, sin ningun estado en memoria.
    with TestClient(app) as nueva:
        _vencer_todo(db_session)
        assert asiento(nueva, "C-3")["disponible"] is True
