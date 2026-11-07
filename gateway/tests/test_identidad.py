"""4.3 Descarte de headers de identidad, JWT local y rutas protegidas."""

from tests.conftest import token


def test_header_de_rol_falsificado_sin_token_se_descarta(client):
    r = client.get("/api/eventos", headers={"X-User-Role": "administrador", "X-User-Id": "1"})
    assert r.status_code == 200
    assert r.json()["x_user_role"] is None
    assert r.json()["x_user_id"] is None


def test_rol_falsificado_con_token_de_cliente_prevalece_el_token(client):
    r = client.get(
        "/api/eventos",
        headers={"Authorization": f"Bearer {token(sub='7', rol='cliente')}",
                 "X-User-Role": "administrador", "X-User-Id": "1"},
    )
    assert r.json()["x_user_role"] == "cliente"
    assert r.json()["x_user_id"] == "7"


def test_token_valido_agrega_identidad(client):
    r = client.get("/api/ventas/compras", headers={"Authorization": f"Bearer {token(sub='42', rol='cliente')}"})
    assert r.status_code == 200
    assert (r.json()["x_user_id"], r.json()["x_user_role"]) == ("42", "cliente")


def test_token_expirado_responde_401_sin_llamar_al_servicio(client, servicios):
    r = client.get("/api/ventas/compras", headers={"Authorization": f"Bearer {token(minutos=-1)}"})
    assert r.status_code == 401
    assert servicios.llamadas == []


def test_token_con_firma_invalida_responde_401(client, servicios):
    adulterado = token(secreto="otro-secreto")
    r = client.get("/api/ventas/compras", headers={"Authorization": f"Bearer {adulterado}"})
    assert r.status_code == 401
    assert servicios.llamadas == []


def test_ruta_protegida_sin_token_responde_401(client, servicios):
    assert client.post("/api/ventas/reservas", json={}).status_code == 401
    assert client.post("/api/eventos", json={}).status_code == 401
    assert servicios.llamadas == []


def test_rutas_publicas_sin_token_se_reenvian_sin_identidad(client):
    for metodo, ruta in [
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/registro"),
        ("POST", "/api/auth/refresh"),
        ("GET", "/api/eventos"),
        ("GET", "/api/eventos/5"),
        ("GET", "/api/ventas/eventos/5/disponibilidad"),
    ]:
        r = client.request(metodo, ruta, json={} if metodo == "POST" else None)
        assert r.status_code == 200, ruta
        assert r.json()["x_user_id"] is None


def test_con_auth_caido_un_token_valido_sigue_funcionando(client, servicios):
    servicios.caidos.add("auth")
    r = client.get("/api/eventos", headers={"Authorization": f"Bearer {token()}"})
    assert r.status_code == 200
    assert r.json()["x_user_role"] == "cliente"
