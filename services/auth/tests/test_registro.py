"""5.1 Registro ampliado de clientes."""

import threading

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import servicio
from app.config import get_settings
from app.models import Usuario
from tests.conftest import DATOS_REGISTRO, datos_registro, token_del_email


def test_registro_exitoso_queda_pendiente_y_envia_verificacion(client, db_session, enviador):
    r = client.post("/auth/registro", json=DATOS_REGISTRO)
    assert r.status_code == 201
    assert r.json()["rol"] == "cliente" and "password" not in r.json()

    usuario = db_session.scalar(select(Usuario))
    assert usuario.estado == "pendiente_verificacion"
    assert (usuario.dni, usuario.localidad, usuario.provincia) == ("30123456", "La Plata", "Buenos Aires")

    [email] = enviador.enviados
    assert email.destinatario == "ana@example.com" and "Verificá" in email.asunto
    assert "/verificar?token=" in email.cuerpo and token_del_email(email)


def test_rol_administrador_en_el_cuerpo_se_ignora(client):
    r = client.post("/auth/registro", json=datos_registro(rol="administrador"))
    assert r.status_code == 201 and r.json()["rol"] == "cliente"


def test_email_duplicado_responde_409(client, db_session):
    assert client.post("/auth/registro", json=DATOS_REGISTRO).status_code == 201
    r = client.post("/auth/registro", json=datos_registro(email="ANA@example.com", dni="30999999"))
    assert r.status_code == 409 and "email" in r.json()["detail"]
    assert db_session.scalar(text("SELECT count(*) FROM users")) == 1


def test_dni_duplicado_responde_409(client, db_session):
    client.post("/auth/registro", json=DATOS_REGISTRO)
    r = client.post("/auth/registro", json=datos_registro(email="otra@example.com"))
    assert r.status_code == 409 and "DNI" in r.json()["detail"]
    assert db_session.scalar(text("SELECT count(*) FROM users")) == 1


def test_password_se_guarda_hasheada(client, db_session):
    client.post("/auth/registro", json=DATOS_REGISTRO)
    usuario = db_session.scalar(select(Usuario))
    assert usuario.password_hash != DATOS_REGISTRO["password"]
    assert usuario.password_hash.startswith("$argon2id$")


@pytest.mark.parametrize("campo,valor", [
    ("dni", "123"), ("dni", "30A23456"), ("provincia", "Narnia"), ("fecha_nacimiento", "2999-01-01"),
    ("fecha_nacimiento", "1800-01-01"), ("codigo_postal", "19"), ("telefono", "abc"), ("email", "sin-arroba"),
    ("calle", ""),
])
def test_dato_invalido_responde_422_con_el_campo(client, db_session, campo, valor):
    r = client.post("/auth/registro", json=datos_registro(**{campo: valor}))
    assert r.status_code == 422
    assert any(campo in e["loc"] for e in r.json()["detail"])
    assert db_session.scalar(text("SELECT count(*) FROM users")) == 0


@pytest.mark.parametrize("faltante", ["calle", "localidad", "provincia", "codigo_postal", "dni", "nombre"])
def test_dato_obligatorio_faltante_responde_422(client, faltante):
    datos = dict(DATOS_REGISTRO)
    datos.pop(faltante)
    assert client.post("/auth/registro", json=datos).status_code == 422


def test_piso_depto_es_opcional(client):
    datos = dict(DATOS_REGISTRO)
    datos.pop("piso_depto")
    assert client.post("/auth/registro", json=datos).status_code == 201


def test_codigo_postal_cpa_es_valido(client):
    assert client.post("/auth/registro", json=datos_registro(codigo_postal="B1900ABC")).status_code == 201


@pytest.mark.parametrize("password", ["corta", "password123"])
def test_contrasenia_que_no_cumple_la_politica_responde_422(client, password):
    r = client.post("/auth/registro", json=datos_registro(password=password))
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "password"]


@pytest.mark.concurrencia
@pytest.mark.parametrize("variante", ["email", "dni"])
def test_registros_simultaneos_con_el_mismo_email_o_dni(db_concurrente, variante):
    barrera = threading.Barrier(2)
    resultados = []
    settings = get_settings()

    def registrar(i):
        datos = dict(DATOS_REGISTRO)
        if variante == "dni":
            datos["email"] = f"persona{i}@example.com"  # mismo DNI, distinto email
        else:
            datos["dni"] = f"3000000{i}"  # mismo email, distinto DNI
        email, password = datos.pop("email"), datos.pop("password")
        with Session(db_concurrente) as session:
            barrera.wait()
            try:
                servicio.registrar_cliente(session, settings, servicio.Efectos(), email, password, **datos)
                resultados.append("creado")
            except (servicio.EmailDuplicado, servicio.DniDuplicado):
                resultados.append("409")

    hilos = [threading.Thread(target=registrar, args=(i,)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert sorted(resultados) == ["409", "creado"]
    with db_concurrente.connect() as conexion:
        assert conexion.scalar(text("SELECT count(*) FROM users")) == 1
