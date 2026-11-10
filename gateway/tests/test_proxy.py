"""4.2 Proxy por prefijo, 404, /internal no expuesto, 503 y CORS."""

from tests.conftest import token


def test_reenvia_a_eventos_con_la_ruta_del_servicio(client, servicios):
    r = client.get("/api/eventos", params={"q": "rock"})
    assert r.status_code == 200
    assert r.json()["servicio"] == "eventos"
    assert r.json()["ruta"] == "/eventos"
    assert r.json()["query"] == "q=rock"


def test_reenvia_subrutas_a_cada_servicio(client):
    assert client.post("/api/auth/login", json={}).json()["ruta"] == "/auth/login"
    r = client.get("/api/ventas/compras", headers={"Authorization": f"Bearer {token()}"})
    assert r.json() == r.json() | {"servicio": "ventas", "ruta": "/ventas/compras"}


def test_prefijo_desconocido_responde_404_sin_llamar_servicios(client, servicios):
    r = client.get("/api/pagos/algo", headers={"Authorization": f"Bearer {token()}"})
    assert r.status_code == 404
    assert servicios.llamadas == []


def test_rutas_internas_no_son_alcanzables(client, servicios):
    assert client.post("/internal/inventario", json={}).status_code == 404
    assert client.post("/api/internal/inventario", json={},
                       headers={"Authorization": f"Bearer {token()}"}).status_code == 404
    assert servicios.llamadas == []


def test_servicio_caido_responde_503(client, servicios):
    servicios.caidos.add("eventos")
    assert client.get("/api/eventos").status_code == 503


def test_no_reenvia_el_token_a_los_servicios(client):
    r = client.get("/api/eventos", headers={"Authorization": f"Bearer {token()}"})
    assert r.json()["authorization"] is None


def test_cors_permite_el_origen_del_frontend(crear_gateway):
    client = crear_gateway(cors_origins="http://localhost:3000")
    r = client.options(
        "/api/eventos",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


ORIGEN = {"Origin": "http://localhost:3000"}


def test_los_401_del_gateway_llevan_headers_cors(crear_gateway):
    """Si no los llevan, el navegador bloquea la respuesta y el frontend no
    puede renovar el token ni mostrar el motivo."""
    client = crear_gateway(cors_origins="http://localhost:3000")
    r = client.get("/api/ventas/compras", headers={**ORIGEN, "Authorization": f"Bearer {token(minutos=-1)}"})
    assert r.status_code == 401
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_los_429_llevan_cors_y_exponen_retry_after(crear_gateway):
    client = crear_gateway(cors_origins="http://localhost:3000", rate_limit_auth=1)
    client.post("/api/auth/login", json={}, headers=ORIGEN)
    r = client.post("/api/auth/login", json={}, headers=ORIGEN)
    assert r.status_code == 429
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "retry-after" in r.headers["access-control-expose-headers"].lower()
