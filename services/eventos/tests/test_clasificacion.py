"""Clasificacion del evento (tipo, organizador, participantes, descripcion),
catalogo de tipos y estado calculado."""

import pytest
from sqlalchemy import func, select, text

from app.models import Organizador, Participante
from tests.helpers import datos_evento

OWNER = {"X-User-Id": "10", "X-User-Role": "event_owner"}


@pytest.fixture
def recinto(client):
    return client.post("/eventos/recintos", json={"nombre": "Estadio"}, headers=OWNER).json()


def _crear(client, recinto, **cambios):
    return client.post("/eventos", json=datos_evento(recinto["id"], **cambios), headers=OWNER)


def _contar(db_session, modelo) -> int:
    return db_session.scalar(select(func.count()).select_from(modelo))


# --- Alta con clasificacion -------------------------------------------------------

def test_alta_completa(client, recinto):
    r = _crear(client, recinto, tipo="recital", organizador="DF Entertainment",
               participantes=["Los Piojos", "Ciro"], descripcion="Vuelta a los escenarios")
    assert r.status_code == 201
    evento = r.json()
    assert evento["estado"] == "borrador" and evento["owner_id"] == 10
    assert evento["tipo"] == "recital"
    assert evento["organizador"]["nombre"] == "DF Entertainment"
    assert sorted(p["nombre"] for p in evento["participantes"]) == ["Ciro", "Los Piojos"]
    assert evento["descripcion"] == "Vuelta a los escenarios"


def test_detalle_incluye_la_clasificacion(client, recinto):
    creado = _crear(client, recinto, participantes=["Los Piojos"]).json()
    detalle = client.get(f"/eventos/{creado['id']}", headers=OWNER).json()
    assert {"tipo", "organizador", "participantes", "descripcion", "estado"} <= detalle.keys()


@pytest.mark.parametrize("falta", ["tipo", "organizador"])
def test_alta_sin_tipo_u_organizador_responde_422(client, recinto, falta, db_session):
    datos = datos_evento(recinto["id"])
    del datos[falta]
    assert client.post("/eventos", json=datos, headers=OWNER).status_code == 422
    assert db_session.scalar(text("SELECT count(*) FROM eventos")) == 0


def test_tipo_inexistente_responde_422_sin_dejar_nada_creado(client, recinto, db_session):
    r = _crear(client, recinto, tipo="stand-up", organizador="Nuevo", participantes=["Alguien"])
    assert r.status_code == 422
    assert db_session.scalar(text("SELECT count(*) FROM eventos")) == 0
    assert _contar(db_session, Organizador) == 0 and _contar(db_session, Participante) == 0


@pytest.mark.parametrize("cambios", [{"organizador": "   "}, {"participantes": ["Ciro", ""]}])
def test_organizador_o_participante_vacio_responde_422(client, recinto, cambios, db_session):
    assert _crear(client, recinto, **cambios).status_code == 422
    assert db_session.scalar(text("SELECT count(*) FROM eventos")) == 0


def test_participante_repetido_queda_una_sola_vez(client, recinto):
    evento = _crear(client, recinto, participantes=["Ciro", " ciro ", "Los Piojos"]).json()
    assert sorted(p["nombre"] for p in evento["participantes"]) == ["Ciro", "Los Piojos"]


def test_participantes_y_organizador_se_reutilizan_entre_eventos(client, recinto, db_session):
    uno = _crear(client, recinto, organizador="DF Entertainment", participantes=["Los Piojos"]).json()
    otro = _crear(client, recinto, organizador="df entertainment", participantes=[" los piojos "]).json()
    assert uno["organizador"]["id"] == otro["organizador"]["id"]
    assert uno["participantes"][0]["id"] == otro["participantes"][0]["id"]
    assert _contar(db_session, Organizador) == 1 and _contar(db_session, Participante) == 1


# --- Catalogo de tipos ------------------------------------------------------------

def test_listado_publico_de_tipos(client):
    r = client.get("/eventos/tipos")  # sin identidad
    assert r.status_code == 200
    assert {t["codigo"]: t["nombre"] for t in r.json()} == {
        "recital": "Recital", "teatro": "Teatro", "deporte": "Deporte",
        "conferencia": "Conferencia", "festival": "Festival", "otro": "Otro",
    }


def test_alta_con_un_tipo_agregado_al_catalogo(client, recinto, db_session):
    db_session.execute(text("INSERT INTO tipos_evento (codigo, nombre) VALUES ('stand-up', 'Stand-up')"))
    r = _crear(client, recinto, tipo="stand-up")
    assert r.status_code == 201 and r.json()["tipo"] == "stand-up"
    assert "stand-up" in {t["codigo"] for t in client.get("/eventos/tipos").json()}


# --- Estado calculado -------------------------------------------------------------

def _con_fecha(db_session, evento_id: int, estado: str, intervalo: str) -> None:
    db_session.execute(
        text(f"UPDATE eventos SET estado = :s, fecha = now() + interval '{intervalo}' WHERE id = :e"),
        {"s": estado, "e": evento_id},
    )
    db_session.expire_all()


def _estado(client, evento_id: int) -> str:
    return client.get(f"/eventos/{evento_id}", headers=OWNER).json()["estado"]


def test_publicado_a_futuro_se_informa_publicado(client, recinto, db_session):
    evento = _crear(client, recinto).json()
    _con_fecha(db_session, evento["id"], "publicado", "1 day")
    assert _estado(client, evento["id"]) == "publicado"


def test_publicado_con_fecha_pasada_se_informa_finalizado(client, recinto, db_session):
    evento = _crear(client, recinto).json()
    _con_fecha(db_session, evento["id"], "publicado", "-1 hour")
    assert _estado(client, evento["id"]) == "finalizado"
    mios = {e["id"]: e["estado"] for e in client.get("/eventos/mios", headers=OWNER).json()}
    assert mios[evento["id"]] == "finalizado"


def test_borrador_con_fecha_pasada_sigue_borrador(client, recinto, db_session):
    evento = _crear(client, recinto).json()
    _con_fecha(db_session, evento["id"], "borrador", "-1 hour")
    assert _estado(client, evento["id"]) == "borrador"
