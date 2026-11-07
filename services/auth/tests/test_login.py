"""5.3 Login y emision de tokens."""

import jwt
import pytest

from app.config import get_settings

DATOS = {"email": "ana@example.com", "password": "clave-segura-1"}


@pytest.fixture
def registrado(client):
    client.post("/auth/registro", json=DATOS)
    return client


def _decodificar(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def test_login_exitoso_emite_access_y_refresh(registrado):
    r = registrado.post("/auth/login", json=DATOS)
    assert r.status_code == 200
    cuerpo = r.json()
    datos = _decodificar(cuerpo["access_token"])
    assert datos["rol"] == "cliente" and datos["sub"].isdigit() and "exp" in datos
    assert len(cuerpo["refresh_token"]) >= 32


def test_password_incorrecta_y_email_inexistente_dan_la_misma_respuesta(registrado):
    mala = registrado.post("/auth/login", json={**DATOS, "password": "otra-clave-123"})
    inexistente = registrado.post("/auth/login", json={"email": "nadie@example.com", "password": "x" * 10})
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json()


def test_expiracion_por_defecto_es_2_horas(registrado):
    datos = _decodificar(registrado.post("/auth/login", json=DATOS).json()["access_token"])
    assert datos["exp"] - datos["iat"] == 2 * 60 * 60


def test_expiracion_configurable(registrado, monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_access_ttl_minutes", 30)
    r = registrado.post("/auth/login", json=DATOS)
    datos = _decodificar(r.json()["access_token"])
    assert datos["exp"] - datos["iat"] == 30 * 60
    assert r.json()["expires_in"] == 30 * 60
