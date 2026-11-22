"""Actualizacion versionada del evento: PUT /internal/eventos/{id}."""

import pytest
from sqlalchemy import text

from tests.helpers import EVENTO, inventario

FECHA_ORIGINAL = "2026-12-20T21:00:00+00:00"


@pytest.fixture
def con_inventario(client):
    client.post("/internal/inventario", json={**inventario(), "fecha_inicio": FECHA_ORIGINAL})
    return client


def _estado(db_session, evento_id: int = EVENTO):
    fecha, cancelado, version = db_session.execute(
        text("SELECT fecha_inicio, cancelado, version FROM inventario_eventos WHERE evento_id = :e"),
        {"e": evento_id},
    ).one()
    return fecha.isoformat() if fecha else None, cancelado, version


def _actualizar(client, cuerpo: dict, evento_id: int = EVENTO):
    return client.put(f"/internal/eventos/{evento_id}", json=cuerpo)


def test_cambio_de_fecha(con_inventario, db_session):
    r = _actualizar(con_inventario, {"version": 2, "fecha_inicio": "2026-12-27T21:00:00+00:00"})
    assert r.status_code == 200 and r.json()["aplicado"] is True
    assert _estado(db_session) == ("2026-12-27T21:00:00+00:00", False, 2)


def test_cambio_reenviado_no_cambia_nada(con_inventario, db_session):
    cuerpo = {"version": 2, "fecha_inicio": "2026-12-27T21:00:00+00:00"}
    _actualizar(con_inventario, cuerpo)
    r = _actualizar(con_inventario, cuerpo)
    assert r.status_code == 200 and r.json()["aplicado"] is False
    assert _estado(db_session) == ("2026-12-27T21:00:00+00:00", False, 2)


def test_version_vieja_que_llega_tarde_se_ignora(con_inventario, db_session):
    _actualizar(con_inventario, {"version": 3, "fecha_inicio": "2027-01-03T21:00:00+00:00"})
    r = _actualizar(con_inventario, {"version": 2, "fecha_inicio": "2026-12-27T21:00:00+00:00"})
    assert r.status_code == 200 and r.json()["aplicado"] is False
    assert _estado(db_session) == ("2027-01-03T21:00:00+00:00", False, 3)


def test_cancelacion(con_inventario, db_session):
    r = _actualizar(con_inventario, {"version": 2, "cancelado": True})
    assert r.status_code == 200 and r.json()["aplicado"] is True
    assert _estado(db_session) == (FECHA_ORIGINAL, True, 2)


def test_reprogramacion_posterior_a_una_cancelacion_no_la_revierte(con_inventario, db_session):
    _actualizar(con_inventario, {"version": 3, "cancelado": True})
    r = _actualizar(con_inventario, {"version": 4, "fecha_inicio": "2027-01-03T21:00:00+00:00"})
    assert r.status_code == 200
    fecha, cancelado, _ = _estado(db_session)
    assert cancelado is True and fecha == FECHA_ORIGINAL


def test_evento_sin_inventario_responde_404_y_no_crea_nada(client, db_session):
    r = _actualizar(client, {"version": 1, "cancelado": True}, evento_id=999)
    assert r.status_code == 404
    assert db_session.scalar(text("SELECT count(*) FROM inventario_eventos")) == 0


@pytest.mark.parametrize("cuerpo", [
    {"cancelado": True},                       # sin version
    {"version": 0, "cancelado": True},         # version no positiva
    {"version": 2},                            # sin ningun cambio
])
def test_cuerpo_invalido_responde_422(con_inventario, cuerpo):
    assert _actualizar(con_inventario, cuerpo).status_code == 422
