"""10.1 Revocacion inmediata y 10.2 rutas de recuperacion de cuenta."""

import time

import pytest

from tests.conftest import token

RECUPERACION = [
    "/api/auth/verificar-email",
    "/api/auth/reenviar-verificacion",
    "/api/auth/olvide-contrasenia",
    "/api/auth/restablecer-contrasenia",
]


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


# --- 10.1 Revocacion ------------------------------------------------------------

def test_token_emitido_antes_de_la_revocacion_es_rechazado(client, servicios, redis_sync):
    ahora = int(time.time())
    redis_sync.set("revocado:7", ahora)
    r = client.get("/api/ventas/compras", headers=_auth(token(sub="7", iat=ahora - 1800)))
    assert r.status_code == 401 and "revocada" in r.json()["detail"]
    assert servicios.llamadas == []


def test_token_emitido_despues_de_la_revocacion_es_aceptado(client, redis_sync):
    ahora = int(time.time())
    redis_sync.set("revocado:7", ahora - 900)
    assert client.get("/api/ventas/compras", headers=_auth(token(sub="7", iat=ahora))).status_code == 200


def test_token_del_mismo_segundo_es_aceptado(client, redis_sync):
    ahora = int(time.time())
    redis_sync.set("revocado:7", ahora)
    assert client.get("/api/ventas/compras", headers=_auth(token(sub="7", iat=ahora))).status_code == 200


def test_la_revocacion_es_por_usuario(client, redis_sync):
    ahora = int(time.time())
    redis_sync.set("revocado:7", ahora)
    assert client.get("/api/ventas/compras", headers=_auth(token(sub="8", iat=ahora - 60))).status_code == 200


def test_la_revocacion_tambien_aplica_en_rutas_publicas_con_token(client, redis_sync):
    ahora = int(time.time())
    redis_sync.set("revocado:7", ahora)
    assert client.get("/api/eventos", headers=_auth(token(sub="7", iat=ahora - 60))).status_code == 401


def test_redis_caido_deja_pasar(crear_gateway, capsys):
    client = crear_gateway(redis_url="redis://127.0.0.1:1/0")
    assert client.get("/api/ventas/compras", headers=_auth(token())).status_code == 200
    assert "revocacion sin Redis" in capsys.readouterr().out


def test_la_rechazada_queda_en_la_bitacora(client, redis_sync, engine_sync):
    from tests.conftest import filas_bitacora
    ahora = int(time.time())
    redis_sync.set("revocado:7", ahora)
    client.get("/api/ventas/compras", headers=_auth(token(sub="7", iat=ahora - 60)))
    assert [f["status"] for f in filas_bitacora(engine_sync)] == [401]


# --- 10.2 Rutas de recuperacion -------------------------------------------------------

@pytest.mark.parametrize("ruta", RECUPERACION)
def test_las_rutas_de_recuperacion_son_publicas(client, ruta):
    r = client.post(ruta, json={})
    assert r.status_code == 200
    assert r.json()["x_user_id"] is None
    assert r.json()["ruta"] == ruta.removeprefix("/api")


@pytest.mark.parametrize("ruta", RECUPERACION)
def test_comparten_el_limite_del_grupo_auth(crear_gateway, servicios, ruta):
    client = crear_gateway(rate_limit_auth=2)
    client.post("/api/auth/login", json={})
    client.post("/api/auth/login", json={})
    r = client.post(ruta, json={})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert len(servicios.llamadas) == 2


def test_abuso_del_pedido_de_restablecimiento(crear_gateway, servicios):
    client = crear_gateway(rate_limit_auth=3)
    codigos = [client.post("/api/auth/olvide-contrasenia", json={}).status_code for _ in range(4)]
    assert codigos == [200, 200, 200, 429]


def test_perfil_y_admin_siguen_exigiendo_token(client, servicios):
    assert client.get("/api/auth/perfil").status_code == 401
    assert client.get("/api/auth/admin/usuarios").status_code == 401
    assert servicios.llamadas == []
