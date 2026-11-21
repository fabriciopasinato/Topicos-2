"""Edicion de datos descriptivos: PATCH /eventos/{id}."""

import pytest
from sqlalchemy import text

from app.cliente_ventas import get_cliente_ventas
from app.main import app
from tests.helpers import datos_evento, fecha_futura

OWNER = {"X-User-Id": "10", "X-User-Role": "event_owner"}


class VentasQueNoDebeLlamarse:
    """Si la edicion llamara a ventas, el test falla."""

    def __getattr__(self, nombre):
        raise AssertionError(f"la edicion no debe llamar a ventas (se llamo {nombre})")


@pytest.fixture
def sin_ventas(client):
    app.dependency_overrides[get_cliente_ventas] = lambda: VentasQueNoDebeLlamarse()


@pytest.fixture
def recintos(client):
    return [client.post("/eventos/recintos", json={"nombre": n}, headers=OWNER).json()["id"] for n in ("A", "B")]


@pytest.fixture
def evento(client, recintos):
    return client.post("/eventos", json=datos_evento(recintos[0], participantes=["Ciro"]), headers=OWNER).json()


def _estado(db_session, evento_id: int, estado: str, intervalo: str = "30 days") -> None:
    db_session.execute(
        text(f"UPDATE eventos SET estado = :s, fecha = now() + interval '{intervalo}' WHERE id = :e"),
        {"s": estado, "e": evento_id},
    )
    db_session.expire_all()


def _editar(client, evento_id: int, cambios: dict):
    return client.patch(f"/eventos/{evento_id}", json=cambios, headers=OWNER)


def test_edicion_de_un_borrador(client, evento, recintos):
    r = _editar(client, evento["id"], {
        "nombre": "Nuevo nombre", "descripcion": "Otra", "tipo": "festival",
        "organizador": "Fenix", "participantes": ["Los Piojos"], "recinto_id": recintos[1],
    })
    assert r.status_code == 200
    e = r.json()
    assert (e["nombre"], e["descripcion"], e["tipo"]) == ("Nuevo nombre", "Otra", "festival")
    assert e["organizador"]["nombre"] == "Fenix"
    assert [p["nombre"] for p in e["participantes"]] == ["Los Piojos"]
    assert e["recinto"]["id"] == recintos[1]


def test_campos_ausentes_no_cambian(client, evento):
    r = _editar(client, evento["id"], {"descripcion": "Solo esto"})
    e = r.json()
    assert e["nombre"] == evento["nombre"] and e["tipo"] == evento["tipo"]
    assert [p["nombre"] for p in e["participantes"]] == ["Ciro"]


def test_edicion_de_un_evento_publicado_no_avisa_a_ventas(client, evento, db_session, sin_ventas):
    _estado(db_session, evento["id"], "publicado")
    r = _editar(client, evento["id"], {"descripcion": "Con invitados", "participantes": ["Ciro", "Los Piojos"]})
    assert r.status_code == 200
    assert r.json()["descripcion"] == "Con invitados"
    assert sorted(p["nombre"] for p in r.json()["participantes"]) == ["Ciro", "Los Piojos"]


def test_fecha_en_la_edicion_responde_422(client, evento):
    r = _editar(client, evento["id"], {"nombre": "X", "fecha": fecha_futura(60)})
    assert r.status_code == 422
    assert "reprogramar" in str(r.json()["detail"])
    assert client.get(f"/eventos/{evento['id']}", headers=OWNER).json()["nombre"] == evento["nombre"]


def test_recinto_de_un_evento_publicado_responde_409(client, evento, recintos, db_session):
    _estado(db_session, evento["id"], "publicado")
    r = _editar(client, evento["id"], {"recinto_id": recintos[1]})
    assert r.status_code == 409
    assert client.get(f"/eventos/{evento['id']}", headers=OWNER).json()["recinto"]["id"] == recintos[0]


def test_mismo_recinto_en_un_evento_publicado_no_es_un_cambio(client, evento, recintos, db_session):
    _estado(db_session, evento["id"], "publicado")
    assert _editar(client, evento["id"], {"recinto_id": recintos[0], "nombre": "Ok"}).status_code == 200


@pytest.mark.parametrize("estado, intervalo", [("publicado", "-1 hour"), ("cancelado", "30 days")])
def test_evento_finalizado_o_cancelado_no_se_edita(client, evento, db_session, estado, intervalo):
    _estado(db_session, evento["id"], estado, intervalo)
    assert _editar(client, evento["id"], {"nombre": "Otro"}).status_code == 409
    assert db_session.scalar(text("SELECT nombre FROM eventos WHERE id = :e"), {"e": evento["id"]}) == evento["nombre"]


@pytest.mark.parametrize("cambios", [{"tipo": "stand-up"}, {"organizador": "  "}, {"recinto_id": 999}])
def test_dato_invalido_responde_422_y_no_cambia_nada(client, evento, cambios):
    r = _editar(client, evento["id"], {"nombre": "No deberia quedar", **cambios})
    assert r.status_code == 422
    assert client.get(f"/eventos/{evento['id']}", headers=OWNER).json()["nombre"] == evento["nombre"]
