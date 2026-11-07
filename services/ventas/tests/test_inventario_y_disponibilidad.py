"""7.2 Recepcion del inventario y 7.3 disponibilidad efectiva."""

import pytest
from sqlalchemy import text

from tests.helpers import ZONA_GENERAL, ZONA_NUMERADA, asiento, disponibilidad, inventario, reservar


@pytest.fixture
def con_inventario(client):
    client.post("/internal/inventario", json=inventario())
    return client


def test_inventario_nuevo_crea_un_ticket_por_entrada(client, db_session):
    r = client.post("/internal/inventario", json=inventario(filas=("A", "B", "C"), por_fila=10, capacidad_general=500))
    assert r.status_code == 200 and r.json()["creado"] is True
    conteo = dict(db_session.execute(text(
        "SELECT tipo_zona, count(*) FROM tickets WHERE estado = 'disponible' GROUP BY tipo_zona"
    )).all())
    assert conteo == {"numerada": 30, "general": 500}


def test_inventario_reenviado_no_duplica(client, db_session):
    client.post("/internal/inventario", json=inventario())
    r = client.post("/internal/inventario", json=inventario())
    assert r.status_code == 200 and r.json()["creado"] is False
    assert db_session.scalar(text("SELECT count(*) FROM tickets")) == 40


def test_los_tickets_guardan_copia_del_precio(con_inventario, db_session):
    precios = dict(db_session.execute(text("SELECT DISTINCT tipo_zona, precio FROM tickets")).all())
    assert float(precios["numerada"]) == 1500.0 and float(precios["general"]) == 800.0


def test_disponibilidad_de_evento_inexistente_responde_404(client):
    assert client.get("/ventas/eventos/999/disponibilidad").status_code == 404


def test_disponibilidad_tras_una_venta(con_inventario, db_session):
    db_session.execute(text("UPDATE tickets SET estado = 'vendido' WHERE fila = 'A' AND numero = 5"))
    assert asiento(con_inventario, "A-5")["disponible"] is False
    assert all(asiento(con_inventario, f"A-{n}")["disponible"] for n in (1, 2, 3, 4, 6, 7, 8, 9, 10))


def test_asiento_con_reserva_vigente_no_esta_disponible(con_inventario):
    reservar(con_inventario, asientos=["A-6"])
    assert asiento(con_inventario, "A-6")["disponible"] is False


def test_asiento_con_reserva_vencida_esta_disponible(con_inventario, db_session):
    reservar(con_inventario, asientos=["A-6"])
    db_session.execute(text("UPDATE tickets SET reservado_hasta = now() - interval '1 minute' WHERE reserva_id IS NOT NULL"))
    assert asiento(con_inventario, "A-6")["disponible"] is True


def test_cantidad_restante_por_zona_general(con_inventario):
    reservar(con_inventario, generales=[(ZONA_GENERAL, 3)])
    zonas = disponibilidad(con_inventario)
    assert zonas[ZONA_GENERAL]["disponibles"] == 7 and zonas[ZONA_GENERAL]["total"] == 10
    assert zonas[ZONA_NUMERADA]["disponibles"] == 30


def test_la_ruta_interna_no_esta_bajo_el_prefijo_publico(client):
    # El gateway solo reenvia /api/ventas/* -> /ventas/*; el inventario vive en
    # /internal/*, fuera de ese prefijo (ver gateway/tests/test_proxy.py).
    assert client.post("/ventas/internal/inventario", json=inventario()).status_code in (404, 405)
