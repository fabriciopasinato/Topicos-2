"""Borrado de borradores: DELETE /eventos/{id}."""

import pytest
from sqlalchemy import func, select, text

from app.models import Asiento, Organizador, Participante, Sector, Zona
from tests.helpers import datos_evento

OWNER = {"X-User-Id": "10", "X-User-Role": "event_owner"}
OTRO_OWNER = {"X-User-Id": "11", "X-User-Role": "event_owner"}
CLIENTE = {"X-User-Id": "20", "X-User-Role": "cliente"}


@pytest.fixture
def recinto(client):
    return client.post("/eventos/recintos", json={"nombre": "Estadio"}, headers=OWNER).json()["id"]


def _evento_con_zonas(client, recinto, **cambios) -> int:
    evento_id = client.post("/eventos", json=datos_evento(recinto, **cambios), headers=OWNER).json()["id"]
    sector = client.post(f"/eventos/{evento_id}/sectores", json={"nombre": "Platea"}, headers=OWNER).json()
    client.post(f"/eventos/{evento_id}/sectores/{sector['id']}/zonas", headers=OWNER,
                json={"nombre": "A", "tipo": "numerada", "precio": "10", "filas": ["A"], "asientos_por_fila": 5})
    return evento_id


def _contar(db_session, modelo) -> int:
    return db_session.scalar(select(func.count()).select_from(modelo))


def test_borrado_de_un_borrador(client, recinto, db_session):
    evento_id = _evento_con_zonas(client, recinto, participantes=["Ciro"])
    r = client.delete(f"/eventos/{evento_id}", headers=OWNER)
    assert r.status_code == 204
    assert client.get(f"/eventos/{evento_id}", headers=OWNER).status_code == 404
    assert (_contar(db_session, Sector), _contar(db_session, Zona), _contar(db_session, Asiento)) == (0, 0, 0)
    assert db_session.scalar(text("SELECT count(*) FROM evento_participantes")) == 0


def test_organizadores_y_participantes_compartidos_siguen_existiendo(client, recinto, db_session):
    borrado = _evento_con_zonas(client, recinto, organizador="Fenix", participantes=["Ciro"])
    otro = _evento_con_zonas(client, recinto, organizador="Fenix", participantes=["Ciro"])
    client.delete(f"/eventos/{borrado}", headers=OWNER)
    assert _contar(db_session, Organizador) == 1 and _contar(db_session, Participante) == 1
    detalle = client.get(f"/eventos/{otro}", headers=OWNER).json()
    assert detalle["organizador"]["nombre"] == "Fenix" and detalle["participantes"][0]["nombre"] == "Ciro"


@pytest.mark.parametrize("estado", ["publicado", "cancelado"])
def test_publicado_o_cancelado_no_se_borra(client, recinto, db_session, estado):
    evento_id = _evento_con_zonas(client, recinto)
    db_session.execute(text("UPDATE eventos SET estado = :s WHERE id = :e"), {"s": estado, "e": evento_id})
    db_session.expire_all()
    assert client.delete(f"/eventos/{evento_id}", headers=OWNER).status_code == 409
    assert db_session.scalar(text("SELECT count(*) FROM eventos")) == 1


@pytest.mark.parametrize("headers, codigo", [(OTRO_OWNER, 403), (CLIENTE, 403)])
def test_permisos(client, recinto, db_session, headers, codigo):
    evento_id = _evento_con_zonas(client, recinto)
    assert client.delete(f"/eventos/{evento_id}", headers=headers).status_code == codigo
    assert db_session.scalar(text("SELECT count(*) FROM eventos")) == 1
