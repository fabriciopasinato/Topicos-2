"""4.5 Bitacora de cada solicitud, antes de responder, con fail-open."""

import json

from tests.conftest import filas_bitacora, token


def test_registra_solicitud_exitosa_con_todos_los_datos(client, engine_sync):
    client.get("/api/ventas/compras", headers={"Authorization": f"Bearer {token(sub='42')}"})
    [fila] = filas_bitacora(engine_sync)
    assert fila["ip"] == "testclient"
    assert fila["metodo"] == "GET"
    assert fila["ruta"] == "/api/ventas/compras"
    assert fila["user_id"] == "42"
    assert fila["status"] == 200
    assert fila["duracion_ms"] > 0


def test_registra_401(client, engine_sync):
    client.post("/api/ventas/reservas", json={})
    assert [f["status"] for f in filas_bitacora(engine_sync)] == [401]


def test_registra_429(crear_gateway, engine_sync):
    client = crear_gateway(rate_limit_general=1)
    client.get("/api/eventos")
    client.get("/api/eventos")
    assert [f["status"] for f in filas_bitacora(engine_sync)] == [200, 429]


def test_registra_503_si_el_servicio_esta_caido(client, servicios, engine_sync):
    servicios.caidos.add("eventos")
    client.get("/api/eventos")
    assert [f["status"] for f in filas_bitacora(engine_sync)] == [503]


def test_el_registro_existe_cuando_llega_la_respuesta(client, engine_sync):
    # La escritura es sincronica: al recibir la respuesta, la fila ya esta.
    for i in range(5):
        client.get("/api/eventos")
        assert len(filas_bitacora(engine_sync)) == i + 1


def test_health_no_se_registra(client, engine_sync):
    client.get("/health")
    assert filas_bitacora(engine_sync) == []


def test_con_gateway_db_caida_responde_igual_y_registra_en_stdout(crear_gateway, capsys):
    client = crear_gateway(database_url="postgresql+asyncpg://x:x@127.0.0.1:1/x_test")
    r = client.get("/api/eventos")
    assert r.status_code == 200
    lineas = [l for l in capsys.readouterr().out.splitlines() if "bitacora_no_persistida" in l]
    registro = json.loads(lineas[-1])
    assert registro["ruta"] == "/api/eventos" and registro["status"] == 200
