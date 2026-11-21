"""6.2 Gestion de eventos, sectores y zonas con autorizacion por rol y duenio."""

import pytest

from tests.helpers import datos_evento

OWNER = {"X-User-Id": "10", "X-User-Role": "event_owner"}
OTRO_OWNER = {"X-User-Id": "11", "X-User-Role": "event_owner"}
ADMIN = {"X-User-Id": "1", "X-User-Role": "administrador"}
CLIENTE = {"X-User-Id": "20", "X-User-Role": "cliente"}


@pytest.fixture
def recinto(client):
    return client.post("/eventos/recintos", json={"nombre": "Estadio"}, headers=OWNER).json()


@pytest.fixture
def evento(client, recinto):
    return client.post("/eventos", json=datos_evento(recinto["id"]), headers=OWNER).json()


@pytest.fixture
def sector(client, evento):
    return client.post(f"/eventos/{evento['id']}/sectores", json={"nombre": "Platea"}, headers=OWNER).json()


def test_owner_crea_evento_en_borrador(evento):
    assert evento["estado"] == "borrador"
    assert evento["owner_id"] == 10


def test_owner_no_puede_editar_evento_ajeno(client, evento):
    r = client.patch(f"/eventos/{evento['id']}", json={"nombre": "Otro"}, headers=OTRO_OWNER)
    assert r.status_code == 403
    assert client.get(f"/eventos/{evento['id']}", headers=OWNER).json()["nombre"] == "Recital"


def test_owner_ajeno_recibe_403_sobre_evento_publicado(client, evento, db_session):
    from sqlalchemy import text
    db_session.execute(text("UPDATE eventos SET estado = 'publicado'"))
    r = client.patch(f"/eventos/{evento['id']}", json={"nombre": "Otro"}, headers=OTRO_OWNER)
    assert r.status_code == 403


def test_cliente_no_puede_crear_eventos(client, recinto):
    datos = datos_evento(recinto["id"], nombre="X")
    assert client.post("/eventos", json=datos, headers=CLIENTE).status_code == 403


def test_sin_identidad_no_puede_crear(client, recinto):
    datos = datos_evento(recinto["id"], nombre="X")
    assert client.post("/eventos", json=datos).status_code == 401


def test_administrador_edita_cualquier_evento(client, evento):
    r = client.patch(f"/eventos/{evento['id']}", json={"nombre": "Editado por admin"}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["nombre"] == "Editado por admin"


def test_zona_numerada_genera_los_asientos(client, evento, sector):
    zona = {"nombre": "Platea A", "tipo": "numerada", "precio": "1500.00",
            "filas": ["A", "B", "C"], "asientos_por_fila": 10}
    r = client.post(f"/eventos/{evento['id']}/sectores/{sector['id']}/zonas", json=zona, headers=OWNER)
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["capacidad"] == 30 and len(cuerpo["asientos"]) == 30
    assert {(a["fila"], a["numero"]) for a in cuerpo["asientos"]} >= {("A", 1), ("C", 10)}
    assert cuerpo["precio"] == 1500.0


def test_zona_general_con_capacidad(client, evento, sector):
    zona = {"nombre": "Campo", "tipo": "general", "precio": "800", "capacidad": 500}
    r = client.post(f"/eventos/{evento['id']}/sectores/{sector['id']}/zonas", json=zona, headers=OWNER)
    assert r.status_code == 201
    assert r.json()["capacidad"] == 500 and r.json()["asientos"] == []


@pytest.mark.parametrize("zona", [
    {"nombre": "Z", "tipo": "general", "precio": "10", "capacidad": 0},
    {"nombre": "Z", "tipo": "numerada", "precio": "10", "filas": [], "asientos_por_fila": 5},
    {"nombre": "Z", "tipo": "numerada", "precio": "10"},
    {"nombre": "Z", "tipo": "general", "precio": "-1", "capacidad": 10},
])
def test_zona_invalida_responde_422(client, evento, sector, zona):
    r = client.post(f"/eventos/{evento['id']}/sectores/{sector['id']}/zonas", json=zona, headers=OWNER)
    assert r.status_code == 422


def test_recinto_inexistente_responde_422(client):
    datos = datos_evento(999, nombre="X")
    assert client.post("/eventos", json=datos, headers=OWNER).status_code == 422


def test_mis_eventos_lista_solo_los_propios(client, evento, recinto):
    datos = datos_evento(recinto["id"], nombre="Ajeno")
    client.post("/eventos", json=datos, headers=OTRO_OWNER)
    nombres = [e["nombre"] for e in client.get("/eventos/mios", headers=OWNER).json()]
    assert nombres == ["Recital"]
    assert len(client.get("/eventos/mios", headers=ADMIN).json()) == 2
