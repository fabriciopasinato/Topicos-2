"""5.2 Verificacion de email y reenvio."""

from sqlalchemy import text

from tests.conftest import DATOS_REGISTRO, login, token_del_email


def _registrar(client, enviador) -> str:
    client.post("/auth/registro", json=DATOS_REGISTRO)
    return token_del_email(enviador.enviados[-1])


def _estado(db_session) -> str:
    return db_session.execute(text("SELECT estado FROM users")).scalar()


def test_verificacion_exitosa_activa_la_cuenta(client, db_session, enviador):
    token = _registrar(client, enviador)
    assert login(client).json()["codigo"] == "email_no_verificado"

    r = client.post("/auth/verificar-email", json={"token": token})
    assert r.status_code == 200
    assert _estado(db_session) == "activa"
    assert login(client).status_code == 200


def test_token_usado_responde_400(client, db_session, enviador):
    token = _registrar(client, enviador)
    client.post("/auth/verificar-email", json={"token": token})
    assert client.post("/auth/verificar-email", json={"token": token}).status_code == 400


def test_token_vencido_responde_400_y_no_cambia_la_cuenta(client, db_session, enviador):
    token = _registrar(client, enviador)
    db_session.execute(text("UPDATE tokens_cuenta SET expires_at = now() - interval '1 minute'"))
    assert client.post("/auth/verificar-email", json={"token": token}).status_code == 400
    assert _estado(db_session) == "pendiente_verificacion"


def test_token_inventado_responde_400(client):
    assert client.post("/auth/verificar-email", json={"token": "inventado"}).status_code == 400


def test_reenvio_invalida_el_token_anterior(client, db_session, enviador):
    viejo = _registrar(client, enviador)
    r = client.post("/auth/reenviar-verificacion", json={"email": "ANA@example.com"})
    assert r.status_code == 202
    nuevo = token_del_email(enviador.enviados[-1])
    assert nuevo != viejo
    assert client.post("/auth/verificar-email", json={"token": viejo}).status_code == 400
    assert client.post("/auth/verificar-email", json={"token": nuevo}).status_code == 200


def test_reenvio_para_email_inexistente_responde_igual_sin_enviar(client, enviador):
    r = client.post("/auth/reenviar-verificacion", json={"email": "nadie@example.com"})
    assert r.status_code == 202
    assert enviador.enviados == []


def test_reenvio_para_cuenta_ya_verificada_no_envia(client, db_session, enviador):
    token = _registrar(client, enviador)
    client.post("/auth/verificar-email", json={"token": token})
    antes = len(enviador.enviados)
    r = client.post("/auth/reenviar-verificacion", json={"email": DATOS_REGISTRO["email"]})
    assert r.status_code == 202 and len(enviador.enviados) == antes
