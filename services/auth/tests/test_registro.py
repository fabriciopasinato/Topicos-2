"""5.2 Registro publico de clientes."""

import threading

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import servicio
from app.models import Usuario

DATOS = {"email": "ana@example.com", "password": "clave-segura-1"}


def test_registro_exitoso_crea_cliente_sin_devolver_password(client):
    r = client.post("/auth/registro", json=DATOS)
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["email"] == "ana@example.com" and cuerpo["rol"] == "cliente"
    assert "password" not in cuerpo and "password_hash" not in cuerpo


def test_rol_administrador_en_el_cuerpo_se_ignora(client):
    r = client.post("/auth/registro", json={**DATOS, "rol": "administrador"})
    assert r.status_code == 201
    assert r.json()["rol"] == "cliente"


def test_email_duplicado_responde_409(client, db_session):
    assert client.post("/auth/registro", json=DATOS).status_code == 201
    r = client.post("/auth/registro", json={**DATOS, "email": "ANA@example.com"})
    assert r.status_code == 409
    assert db_session.scalar(text("SELECT count(*) FROM users")) == 1


def test_password_se_guarda_hasheada(client, db_session):
    client.post("/auth/registro", json=DATOS)
    usuario = db_session.scalar(select(Usuario))
    assert usuario.password_hash != DATOS["password"]
    assert usuario.password_hash.startswith("$argon2id$")


@pytest.mark.parametrize("datos", [
    {"email": "sin-arroba", "password": "clave-segura-1"},
    {"email": "ana@example.com", "password": "corta"},
])
def test_datos_invalidos_responden_422(client, datos):
    assert client.post("/auth/registro", json=datos).status_code == 422


@pytest.mark.concurrencia
def test_registro_concurrente_del_mismo_email_crea_un_solo_usuario(db_concurrente):
    barrera = threading.Barrier(2)
    resultados = []

    def registrar():
        with Session(db_concurrente) as session:
            barrera.wait()
            try:
                servicio.registrar_cliente(session, "mismo@example.com", "clave-segura-1")
                resultados.append("creado")
            except servicio.EmailDuplicado:
                resultados.append("409")

    hilos = [threading.Thread(target=registrar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert sorted(resultados) == ["409", "creado"]
    with db_concurrente.connect() as conexion:
        assert conexion.scalar(text("SELECT count(*) FROM users")) == 1
