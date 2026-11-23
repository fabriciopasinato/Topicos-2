"""7.1 Olvide mi contrasenia y restablecimiento."""

import pytest
from sqlalchemy import select, text

from app.models import Usuario
from tests.conftest import DATOS_REGISTRO, login, token_del_email

NUEVA = "jirafa-violeta-77"


def _pedir(client, enviador, email=DATOS_REGISTRO["email"]) -> str:
    assert client.post("/auth/olvide-contrasenia", json={"email": email}).status_code == 202
    return token_del_email(enviador.enviados[-1])


def _restablecer(client, token, contrasenia=NUEVA):
    return client.post("/auth/restablecer-contrasenia", json={"token": token, "contrasenia": contrasenia})


def test_pedido_para_email_existente_e_inexistente_responde_igual(client, cliente_activo, enviador):
    enviador.enviados.clear()
    existente = client.post("/auth/olvide-contrasenia", json={"email": "ana@example.com"})
    inexistente = client.post("/auth/olvide-contrasenia", json={"email": "nadie@example.com"})
    assert existente.status_code == inexistente.status_code == 202
    assert existente.json() == inexistente.json()
    [email] = enviador.enviados
    assert email.destinatario == "ana@example.com" and "/restablecer?token=" in email.cuerpo


def test_restablecimiento_exitoso_cambia_la_contrasenia(client, cliente_activo, enviador, redis_test, db_session):
    refresh_viejo = login(client).json()["refresh_token"]
    token = _pedir(client, enviador)
    assert _restablecer(client, token).status_code == 200

    assert login(client).status_code == 401  # la vieja ya no sirve
    assert login(client, password=NUEVA).status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": refresh_viejo}).status_code == 401
    user_id = db_session.scalar(select(Usuario.id))
    assert redis_test.get(f"revocado:{user_id}") is not None


def test_restablecimiento_desbloquea_la_cuenta(client, cliente_activo, enviador, db_session):
    for _ in range(5):
        login(client, password="incorrecta-1234")
    token = token_del_email(enviador.enviados[-1])  # el link vino en el email de bloqueo
    assert _restablecer(client, token).status_code == 200
    fila = db_session.execute(text("SELECT estado, motivo_bloqueo, intentos_fallidos FROM users")).one()
    assert tuple(fila) == ("activa", None, 0)
    assert login(client, password=NUEVA).status_code == 200


def test_restablecimiento_verifica_una_cuenta_pendiente(client, enviador, db_session):
    client.post("/auth/registro", json=DATOS_REGISTRO)
    token = _pedir(client, enviador)
    assert _restablecer(client, token).status_code == 200
    assert db_session.execute(text("SELECT estado FROM users")).scalar() == "activa"


def test_token_reutilizado_responde_400(client, cliente_activo, enviador):
    token = _pedir(client, enviador)
    _restablecer(client, token)
    assert _restablecer(client, token, "otra-frase-larga-9").status_code == 400
    assert login(client, password=NUEVA).status_code == 200


def test_token_vencido_responde_400(client, cliente_activo, enviador, db_session):
    token = _pedir(client, enviador)
    db_session.execute(text("UPDATE tokens_cuenta SET expires_at = now() - interval '1 second'"))
    assert _restablecer(client, token).status_code == 400
    assert login(client).status_code == 200  # la contraseña no cambio


def test_solo_sirve_el_ultimo_pedido(client, cliente_activo, enviador):
    primero = _pedir(client, enviador)
    _pedir(client, enviador)
    assert _restablecer(client, primero).status_code == 400


@pytest.mark.parametrize("contrasenia", ["corta", "password123", "ana@example.com"])
def test_contrasenia_invalida_responde_422_y_no_gasta_el_token(client, cliente_activo, enviador, contrasenia):
    token = _pedir(client, enviador)
    r = _restablecer(client, token, contrasenia)
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "contrasenia"]
    assert _restablecer(client, token).status_code == 200  # el token sigue sirviendo
