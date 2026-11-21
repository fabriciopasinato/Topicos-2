"""Cancelacion y reprogramacion: directas en borrador, por outbox en publicado."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.cliente_ventas import get_cliente_ventas
from app.main import app
from tests.helpers import VentasFalsa, datos_evento, fecha_futura

OWNER = {"X-User-Id": "10", "X-User-Role": "event_owner"}
OTRO_OWNER = {"X-User-Id": "11", "X-User-Role": "event_owner"}
ADMIN = {"X-User-Id": "1", "X-User-Role": "administrador"}
CLIENTE = {"X-User-Id": "20", "X-User-Role": "cliente"}


@pytest.fixture
def ventas(client):
    falsa = VentasFalsa()
    app.dependency_overrides[get_cliente_ventas] = lambda: falsa
    return falsa


@pytest.fixture
def recinto(client):
    return client.post("/eventos/recintos", json={"nombre": "Estadio"}, headers=OWNER).json()["id"]


@pytest.fixture
def borrador(client, recinto):
    return client.post("/eventos", json=datos_evento(recinto), headers=OWNER).json()


@pytest.fixture
def publicado(client, borrador, ventas, db_session):
    """Evento publicado de verdad (con zona y ventas falsa con su inventario)."""
    sector = client.post(f"/eventos/{borrador['id']}/sectores", json={"nombre": "P"}, headers=OWNER).json()
    client.post(f"/eventos/{borrador['id']}/sectores/{sector['id']}/zonas", headers=OWNER,
                json={"nombre": "Campo", "tipo": "general", "precio": "10", "capacidad": 10})
    r = client.post(f"/eventos/{borrador['id']}/publicar", headers=OWNER)
    assert r.status_code == 200
    return r.json()


def _detalle(client, evento_id, headers=OWNER):
    return client.get(f"/eventos/{evento_id}", headers=headers).json()


def _contar_operaciones(db_session) -> int:
    return db_session.scalar(text("SELECT count(*) FROM operaciones_ventas"))


def _cancelar(client, evento_id, headers=OWNER):
    return client.post(f"/eventos/{evento_id}/cancelar", headers=headers)


def _reprogramar(client, evento_id, fecha, headers=OWNER):
    return client.post(f"/eventos/{evento_id}/reprogramar", json={"fecha": fecha}, headers=headers)


# --- Cancelacion -------------------------------------------------------------------

def test_cancelacion_de_un_borrador(client, borrador, ventas, db_session):
    r = _cancelar(client, borrador["id"])
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    assert ventas.recibidos == [] and _contar_operaciones(db_session) == 0


def test_cancelacion_con_ventas_disponible(client, publicado, ventas):
    r = _cancelar(client, publicado["id"])
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    assert r.json()["operaciones_pendientes"] == []
    assert ventas.eventos[publicado["id"]]["cancelado"] is True


def test_cancelacion_con_ventas_caido(client, publicado, ventas, db_session):
    ventas.caida = True
    r = _cancelar(client, publicado["id"])
    assert r.status_code == 202
    assert r.json()["estado"] == "publicado"
    [pendiente] = _detalle(client, publicado["id"])["operaciones_pendientes"]
    assert pendiente["tipo"] == "cancelar" and pendiente["intentos"] == 1
    reintento_en_el_futuro = db_session.scalar(text(
        "SELECT proximo_intento_at > now() AND ultimo_error IS NOT NULL FROM operaciones_ventas"))
    assert reintento_en_el_futuro


def test_el_publico_no_ve_las_operaciones_pendientes(client, publicado, ventas):
    ventas.caida = True
    _cancelar(client, publicado["id"])
    assert _detalle(client, publicado["id"], headers=CLIENTE)["operaciones_pendientes"] == []


def test_cancelacion_repetida_no_registra_otra_operacion(client, publicado, ventas, db_session):
    _cancelar(client, publicado["id"])
    r = _cancelar(client, publicado["id"])
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    assert _contar_operaciones(db_session) == 1


def test_cancelar_con_una_cancelacion_pendiente_no_registra_otra(client, publicado, ventas, db_session):
    ventas.caida = True
    _cancelar(client, publicado["id"])
    assert _cancelar(client, publicado["id"]).status_code == 202
    assert _contar_operaciones(db_session) == 1


def test_cancelacion_de_un_evento_finalizado(client, publicado, ventas, db_session):
    db_session.execute(text("UPDATE eventos SET fecha = now() - interval '1 hour' WHERE id = :e"), {"e": publicado["id"]})
    db_session.expire_all()
    assert _cancelar(client, publicado["id"]).status_code == 409
    assert _contar_operaciones(db_session) == 0


@pytest.mark.parametrize("headers", [OTRO_OWNER, CLIENTE])
def test_cancelacion_sin_permiso(client, borrador, ventas, headers):
    assert _cancelar(client, borrador["id"], headers).status_code == 403
    assert _detalle(client, borrador["id"])["estado"] == "borrador"


def test_administrador_cancela_el_borrador_de_otro_owner(client, borrador, ventas):
    r = _cancelar(client, borrador["id"], ADMIN)
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"


# --- Reprogramacion ----------------------------------------------------------------

def _misma_fecha(a: str, b: str) -> bool:
    return datetime.fromisoformat(a) == datetime.fromisoformat(b)


def test_reprogramacion_de_un_borrador(client, borrador, ventas):
    nueva = fecha_futura(60)
    r = _reprogramar(client, borrador["id"], nueva)
    assert r.status_code == 200 and _misma_fecha(r.json()["fecha"], nueva)
    assert ventas.recibidos == []


def test_reprogramacion_con_ventas_disponible(client, publicado, ventas):
    nueva = fecha_futura(60)
    r = _reprogramar(client, publicado["id"], nueva)
    assert r.status_code == 200 and _misma_fecha(r.json()["fecha"], nueva)
    assert _misma_fecha(ventas.eventos[publicado["id"]]["fecha_inicio"], nueva)


def test_reprogramacion_con_ventas_caido_conserva_la_fecha(client, publicado, ventas):
    ventas.caida = True
    nueva = fecha_futura(60)
    r = _reprogramar(client, publicado["id"], nueva)
    assert r.status_code == 202
    assert _misma_fecha(r.json()["fecha"], publicado["fecha"])
    [pendiente] = r.json()["operaciones_pendientes"]
    assert pendiente["tipo"] == "reprogramar" and _misma_fecha(pendiente["fecha"], nueva)


def test_reprogramacion_a_una_fecha_pasada(client, borrador, ventas):
    pasada = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert _reprogramar(client, borrador["id"], pasada).status_code == 422
    assert _misma_fecha(_detalle(client, borrador["id"])["fecha"], borrador["fecha"])


@pytest.mark.parametrize("sql", [
    "UPDATE eventos SET fecha = now() - interval '1 hour' WHERE id = :e",   # finalizado
    "UPDATE eventos SET estado = 'cancelado' WHERE id = :e",                # cancelado
])
def test_reprogramacion_de_un_finalizado_o_cancelado(client, publicado, ventas, db_session, sql):
    db_session.execute(text(sql), {"e": publicado["id"]})
    db_session.expire_all()
    assert _reprogramar(client, publicado["id"], fecha_futura(60)).status_code == 409
    assert _contar_operaciones(db_session) == 0


def test_cancelacion_pendiente_bloquea_reprogramar_y_editar(client, publicado, ventas, db_session):
    ventas.caida = True
    _cancelar(client, publicado["id"])
    assert _reprogramar(client, publicado["id"], fecha_futura(60)).status_code == 409
    assert client.patch(f"/eventos/{publicado['id']}", json={"nombre": "Otro"}, headers=OWNER).status_code == 409
    assert _contar_operaciones(db_session) == 1


def test_reprogramacion_pendiente_no_bloquea_cancelar(client, publicado, ventas):
    ventas.caida = True
    _reprogramar(client, publicado["id"], fecha_futura(60))
    assert _cancelar(client, publicado["id"]).status_code == 202
    tipos = [op["tipo"] for op in _detalle(client, publicado["id"])["operaciones_pendientes"]]
    assert tipos == ["reprogramar", "cancelar"]


def test_mis_eventos_muestra_las_operaciones_pendientes(client, publicado, borrador, ventas):
    ventas.caida = True
    _cancelar(client, publicado["id"])
    mios = {e["id"]: e for e in client.get("/eventos/mios", headers=OWNER).json()}
    assert [op["tipo"] for op in mios[publicado["id"]]["operaciones_pendientes"]] == ["cancelar"]
