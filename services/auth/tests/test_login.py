"""6.2 Login con estados, last_login_at e iat."""

import jwt
import pytest
from sqlalchemy import text

from app.config import get_settings
from tests.conftest import DATOS_REGISTRO, login


def _decodificar(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def _usuario(db_session):
    return db_session.execute(text("SELECT intentos_fallidos, last_login_at FROM users")).one()


def test_login_exitoso_emite_tokens_y_registra_el_login(client, cliente_activo, db_session):
    r = login(client)
    assert r.status_code == 200
    datos = _decodificar(r.json()["access_token"])
    assert datos["rol"] == "cliente" and datos["sub"].isdigit() and "iat" in datos and "exp" in datos
    assert len(r.json()["refresh_token"]) >= 32
    assert _usuario(db_session).last_login_at is not None


def test_contrasenia_incorrecta_y_email_inexistente_dan_la_misma_respuesta(client, cliente_activo):
    mala = login(client, password="otra-clave-larga")
    inexistente = login(client, email="nadie@example.com", password="x" * 12)
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json()
    assert mala.json()["codigo"] == "credenciales_invalidas"


def test_cuenta_sin_verificar_con_contrasenia_correcta(client):
    client.post("/auth/registro", json=DATOS_REGISTRO)
    r = login(client)
    assert r.status_code == 403 and r.json()["codigo"] == "email_no_verificado"
    assert "access_token" not in r.json()


def test_cuenta_sin_verificar_con_contrasenia_incorrecta_no_revela_el_estado(client, db_session):
    client.post("/auth/registro", json=DATOS_REGISTRO)
    r = login(client, password="otra-clave-larga")
    assert r.status_code == 401 and r.json()["codigo"] == "credenciales_invalidas"
    # Los intentos no se cuentan en cuentas que no estan activas.
    assert _usuario(db_session).intentos_fallidos == 0


def test_cuenta_bloqueada_con_contrasenia_correcta(client, cliente_activo, db_session):
    db_session.execute(text("UPDATE users SET estado = 'bloqueada', motivo_bloqueo = 'intentos_fallidos'"))
    r = login(client)
    assert r.status_code == 403 and r.json()["codigo"] == "cuenta_bloqueada"


def test_cuenta_bloqueada_con_contrasenia_incorrecta_responde_401_generico(client, cliente_activo, db_session):
    db_session.execute(text("UPDATE users SET estado = 'bloqueada', motivo_bloqueo = 'intentos_fallidos'"))
    r = login(client, password="otra-clave-larga")
    assert r.status_code == 401 and r.json()["codigo"] == "credenciales_invalidas"


def test_expiracion_por_defecto_es_2_horas(client, cliente_activo):
    datos = _decodificar(login(client).json()["access_token"])
    assert datos["exp"] - datos["iat"] == 2 * 60 * 60


def test_expiracion_configurable(client, cliente_activo, monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_access_ttl_minutes", 30)
    r = login(client)
    datos = _decodificar(r.json()["access_token"])
    assert datos["exp"] - datos["iat"] == 30 * 60 and r.json()["expires_in"] == 30 * 60


def test_refresh_no_cambia_last_login(client, cliente_activo, db_session):
    tokens = login(client).json()
    db_session.execute(text("UPDATE users SET last_login_at = '2020-01-01T00:00:00Z'"))
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    assert _usuario(db_session).last_login_at.year == 2020


@pytest.mark.parametrize("password", ["", "x"])
def test_login_con_contrasenia_vacia_o_corta_es_credencial_invalida(client, cliente_activo, password):
    assert login(client, password=password).status_code == 401
