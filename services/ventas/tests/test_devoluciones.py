"""Tests de devoluciones: solicitud por cliente, gestion por admin,
liberacion diferenciada por modalidad y ciclo de vida del evento."""

import pytest
from sqlalchemy import text

from tests.helpers import (
    ADMIN, CLIENTE, EVENTO, OTRO_CLIENTE, OWNER, ZONA_GENERAL, asiento, disponibilidad, inventario, reservar,
)


@pytest.fixture
def c(client):
    client.post("/internal/inventario", json={**inventario(capacidad_general=2), "fecha_inicio": "2099-12-20T21:00:00+00:00"})
    return client


def _comprar(c, asientos=(), generales=(), headers=CLIENTE):
    reserva = reservar(c, asientos=asientos, generales=generales, headers=headers).json()
    assert c.post(f"/ventas/reservas/{reserva['id']}/pago", headers=headers).status_code == 201
    compras = c.get("/ventas/compras", headers=headers).json()
    return compras[-1]


# --- Solicitud por cliente -------------------------------------------------------

def test_solicitud_exitosa_numerado_no_libera_todavia(c):
    orden = _comprar(c, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]

    r = c.post("/ventas/devoluciones", json={"orden_item_id": item_id, "motivo": "No puedo asistir"}, headers=CLIENTE)
    assert r.status_code == 201
    dev = r.json()
    assert dev["estado"] == "pendiente"
    assert dev["motivo"] == "No puedo asistir"
    assert dev["tipo_zona"] == "numerada"
    assert dev["fila"] == "A" and dev["numero"] == 1
    assert dev["evento_cancelado"] is False
    assert asiento(c, "A-1")["disponible"] is False


def test_solicitud_exitosa_general_no_cambia_cupo_todavia(c):
    orden = _comprar(c, generales=[(ZONA_GENERAL, 2)])
    assert disponibilidad(c)[ZONA_GENERAL]["disponibles"] == 0
    item_id = orden["tickets"][0]["orden_item_id"]

    r = c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE)
    assert r.status_code == 201
    dev = r.json()
    assert dev["estado"] == "pendiente"
    assert dev["tipo_zona"] == "general"
    assert dev["fila"] is None and dev["numero"] is None
    assert disponibilidad(c)[ZONA_GENERAL]["disponibles"] == 0


def test_solicitud_sobre_evento_iniciado_no_cancelado_responde_409(c, db_session):
    orden = _comprar(c, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]
    db_session.execute(text("UPDATE inventario_eventos SET fecha_inicio = now() - interval '10 minutes'"))

    r = c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE)
    assert r.status_code == 409


def test_solicitud_sobre_evento_cancelado_permitida_incluso_con_fecha_pasada(c, db_session):
    orden = _comprar(c, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]
    db_session.execute(text("UPDATE inventario_eventos SET fecha_inicio = now() - interval '1 day', cancelado = true"))

    r = c.post("/ventas/devoluciones", json={"orden_item_id": item_id, "motivo": "Evento cancelado"}, headers=CLIENTE)
    assert r.status_code == 201
    assert r.json()["evento_cancelado"] is True


def test_solicitud_sobre_evento_sin_fecha_permitida(client):
    client.post("/internal/inventario", json=inventario())
    orden = _comprar(client, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]

    r = client.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE)
    assert r.status_code == 201


def test_solicitud_sobre_compra_ajena_o_inexistente_responde_404(c):
    orden = _comprar(c, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]

    assert c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=OTRO_CLIENTE).status_code == 404
    assert c.post("/ventas/devoluciones", json={"orden_item_id": 99999}, headers=CLIENTE).status_code == 404


def test_solicitud_duplicada_pendiente_o_aprobada_responde_409(c):
    orden = _comprar(c, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]

    primera = c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE)
    assert primera.status_code == 201
    assert c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE).status_code == 409

    # Una vez aprobada, tampoco puede volver a solicitarse sobre el mismo orden_item_id.
    assert c.post(f"/ventas/devoluciones/{primera.json()['id']}/aprobar", headers=ADMIN).status_code == 200
    assert c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE).status_code == 409


def test_nueva_solicitud_tras_rechazo_previo_conserva_historial(c, db_session):
    orden = _comprar(c, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]

    primera = c.post("/ventas/devoluciones", json={"orden_item_id": item_id, "motivo": "Intento 1"}, headers=CLIENTE).json()
    assert c.post(
        f"/ventas/devoluciones/{primera['id']}/rechazar",
        json={"nota": "Falta justificacion"},
        headers=ADMIN,
    ).status_code == 200

    segunda = c.post("/ventas/devoluciones", json={"orden_item_id": item_id, "motivo": "Intento 2"}, headers=CLIENTE)
    assert segunda.status_code == 201
    assert segunda.json()["id"] != primera["id"]
    assert db_session.scalar(text("SELECT count(*) FROM devoluciones WHERE orden_item_id = :i"), {"i": item_id}) == 2


def test_roles_no_autorizados_para_devoluciones(c):
    orden = _comprar(c, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]

    assert c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=ADMIN).status_code == 403
    assert c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=OWNER).status_code == 403
    assert c.get("/ventas/devoluciones", headers=OWNER).status_code == 403

    dev_id = c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE).json()["id"]
    assert c.post(f"/ventas/devoluciones/{dev_id}/aprobar", headers=CLIENTE).status_code == 403
    assert c.post(f"/ventas/devoluciones/{dev_id}/aprobar", headers=OWNER).status_code == 403
    assert c.post(f"/ventas/devoluciones/{dev_id}/rechazar", headers=CLIENTE).status_code == 403
    assert c.post(f"/ventas/devoluciones/{dev_id}/rechazar", headers=OWNER).status_code == 403


# --- Consulta / listado ----------------------------------------------------------

def test_listado_cliente_solo_propias_y_admin_filtra_por_estado(c):
    orden_a = _comprar(c, asientos=["A-1"], headers=CLIENTE)
    orden_b = _comprar(c, asientos=["A-2"], headers=OTRO_CLIENTE)

    dev_a = c.post("/ventas/devoluciones", json={"orden_item_id": orden_a["tickets"][0]["orden_item_id"]}, headers=CLIENTE).json()
    dev_b = c.post("/ventas/devoluciones", json={"orden_item_id": orden_b["tickets"][0]["orden_item_id"]}, headers=OTRO_CLIENTE).json()
    assert c.post(f"/ventas/devoluciones/{dev_b['id']}/rechazar", headers=ADMIN).status_code == 200

    propias_a = c.get("/ventas/devoluciones", headers=CLIENTE).json()
    assert [d["id"] for d in propias_a] == [dev_a["id"]]

    todas = c.get("/ventas/devoluciones", headers=ADMIN).json()
    assert {d["id"] for d in todas} == {dev_a["id"], dev_b["id"]}

    pendientes = c.get("/ventas/devoluciones", params={"estado": "pendiente"}, headers=ADMIN).json()
    assert [d["id"] for d in pendientes] == [dev_a["id"]]

    assert c.get("/ventas/devoluciones", params={"estado": "cualquiera"}, headers=ADMIN).status_code == 422


# --- Aprobacion, liberacion diferenciada y rechazo -------------------------------

def test_aprobar_numerado_libera_asiento_y_permite_reventa_y_segunda_devolucion(c):
    orden_a = _comprar(c, asientos=["A-1"], headers=CLIENTE)
    item_a = orden_a["tickets"][0]["orden_item_id"]
    dev_a = c.post("/ventas/devoluciones", json={"orden_item_id": item_a}, headers=CLIENTE).json()

    r = c.post(f"/ventas/devoluciones/{dev_a['id']}/aprobar", json={"nota": "OK"}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["estado"] == "aprobada"
    assert r.json()["resuelto_por"] == 1
    assert r.json()["nota_resolucion"] == "OK"
    assert r.json()["resuelto_at"] is not None
    assert asiento(c, "A-1")["disponible"] is True

    # Otro cliente compra el mismo asiento A-1 y luego solicita su propia devolucion.
    orden_b = _comprar(c, asientos=["A-1"], headers=OTRO_CLIENTE)
    item_b = orden_b["tickets"][0]["orden_item_id"]
    assert item_b != item_a
    dev_b = c.post("/ventas/devoluciones", json={"orden_item_id": item_b}, headers=OTRO_CLIENTE)
    assert dev_b.status_code == 201
    assert c.post(f"/ventas/devoluciones/{dev_b.json()['id']}/aprobar", headers=ADMIN).status_code == 200
    assert asiento(c, "A-1")["disponible"] is True

    # El historial del cliente A conserva la orden original con devolucion aprobada.
    compras_a = c.get("/ventas/compras", headers=CLIENTE).json()
    assert len(compras_a) == 1
    assert compras_a[0]["tickets"][0]["devolucion"]["estado"] == "aprobada"


def test_aprobar_general_incrementa_cupo_y_permite_recompra(c):
    orden = _comprar(c, generales=[(ZONA_GENERAL, 2)], headers=CLIENTE)
    assert disponibilidad(c)[ZONA_GENERAL]["disponibles"] == 0
    item_id = orden["tickets"][0]["orden_item_id"]

    dev = c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE).json()
    assert c.post(f"/ventas/devoluciones/{dev['id']}/aprobar", headers=ADMIN).status_code == 200
    assert disponibilidad(c)[ZONA_GENERAL]["disponibles"] == 1

    # Otro cliente puede reservar y comprar esa entrada liberada.
    orden_b = _comprar(c, generales=[(ZONA_GENERAL, 1)], headers=OTRO_CLIENTE)
    assert len(orden_b["tickets"]) == 1
    assert disponibilidad(c)[ZONA_GENERAL]["disponibles"] == 0


def test_aprobar_sobre_evento_cancelado_no_reabre_venta(c):
    orden = _comprar(c, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]
    assert c.put(f"/internal/eventos/{EVENTO}", json={"version": 2, "cancelado": True}).status_code == 200

    dev = c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE).json()
    assert c.post(f"/ventas/devoluciones/{dev['id']}/aprobar", headers=ADMIN).status_code == 200
    assert reservar(c, asientos=["A-1"], headers=OTRO_CLIENTE).status_code == 409


def test_aprobar_solicitud_creada_en_termino_despues_del_inicio(c, db_session):
    orden = _comprar(c, asientos=["A-1"])
    item_id = orden["tickets"][0]["orden_item_id"]
    dev = c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE).json()

    db_session.execute(text("UPDATE inventario_eventos SET fecha_inicio = now() - interval '5 minutes'"))
    r = c.post(f"/ventas/devoluciones/{dev['id']}/aprobar", headers=ADMIN)
    assert r.status_code == 200 and r.json()["estado"] == "aprobada"


def test_rechazar_deja_ticket_vendido_y_no_permite_re_resolver(c):
    orden = _comprar(c, asientos=["B-2"])
    item_id = orden["tickets"][0]["orden_item_id"]
    dev = c.post("/ventas/devoluciones", json={"orden_item_id": item_id}, headers=CLIENTE).json()

    r = c.post(f"/ventas/devoluciones/{dev['id']}/rechazar", json={"nota": "Fuera de politica"}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["estado"] == "rechazada"
    assert r.json()["nota_resolucion"] == "Fuera de politica"
    assert asiento(c, "B-2")["disponible"] is False

    assert c.post(f"/ventas/devoluciones/{dev['id']}/aprobar", headers=ADMIN).status_code == 409
    assert c.post(f"/ventas/devoluciones/{dev['id']}/rechazar", headers=ADMIN).status_code == 409
    assert c.post("/ventas/devoluciones/99999/aprobar", headers=ADMIN).status_code == 404
    assert c.post("/ventas/devoluciones/99999/rechazar", headers=ADMIN).status_code == 404
