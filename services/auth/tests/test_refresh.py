"""5.4 Renovacion del token de acceso con rotacion del refresh token."""

import threading

import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import servicio
from app.config import get_settings

DATOS = {"email": "ana@example.com", "password": "clave-segura-1"}


@pytest.fixture
def tokens(client):
    client.post("/auth/registro", json=DATOS)
    return client.post("/auth/login", json=DATOS).json()


def test_refresh_exitoso_entrega_un_par_nuevo(client, tokens):
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    assert r.json()["refresh_token"] != tokens["refresh_token"]
    assert jwt.decode(r.json()["access_token"], get_settings().jwt_secret, algorithms=["HS256"])


def test_refresh_reutilizado_responde_401(client, tokens):
    client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


def test_refresh_expirado_responde_401(client, tokens, db_session):
    db_session.execute(text("UPDATE refresh_tokens SET expires_at = now() - interval '1 minute'"))
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


def test_refresh_desconocido_responde_401(client):
    assert client.post("/auth/refresh", json={"refresh_token": "inventado"}).status_code == 401


def test_refresh_emite_el_rol_actual(client, tokens, db_session):
    db_session.execute(text("UPDATE users SET rol = 'event_owner'"))
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    datos = jwt.decode(r.json()["access_token"], get_settings().jwt_secret, algorithms=["HS256"])
    assert datos["rol"] == "event_owner"


@pytest.mark.concurrencia
def test_refresh_concurrente_con_el_mismo_token_solo_gana_uno(db_concurrente):
    settings = get_settings()
    with Session(db_concurrente) as session:
        servicio.registrar_cliente(session, "conc@example.com", "clave-segura-1")
        refresh = servicio.login(session, settings, "conc@example.com", "clave-segura-1").refresh_token

    barrera = threading.Barrier(2)
    resultados = []

    def renovar():
        with Session(db_concurrente) as session:
            barrera.wait()
            try:
                servicio.refrescar(session, settings, refresh)
                resultados.append("ok")
            except servicio.RefreshInvalido:
                resultados.append("401")

    hilos = [threading.Thread(target=renovar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert sorted(resultados) == ["401", "ok"]
