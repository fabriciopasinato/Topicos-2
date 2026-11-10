"""6.1 Revocacion en Redis y 6.3 bloqueo al 5to intento fallido."""

import logging
import threading
import time

import pytest
import redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import revocacion, servicio
from app.config import get_settings
from app.models import Usuario
from tests.conftest import DATOS_REGISTRO, activar, login


def _estado(db_session):
    return db_session.execute(text("SELECT estado, motivo_bloqueo, intentos_fallidos FROM users")).one()


# --- 6.1 Revocacion -------------------------------------------------------------

def test_publicar_escribe_la_marca_con_instante_y_ttl(redis_test):
    revocacion.publicar(redis_test, 7, ttl_segundos=7200, instante=1_700_000_000)
    assert int(redis_test.get("revocado:7")) == 1_700_000_000
    assert 7190 < redis_test.ttl("revocado:7") <= 7200


def test_revocar_refresh_tokens_los_invalida(client, cliente_activo, db_session):
    refresh = login(client).json()["refresh_token"]
    user_id = db_session.scalar(select(Usuario.id))
    revocacion.revocar_refresh_tokens(db_session, user_id)
    assert client.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401


def test_redis_caido_no_rompe_la_operacion(caplog):
    caido = redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.5)
    with caplog.at_level(logging.ERROR, logger="auth.revocacion"):
        revocacion.publicar(caido, 7, 60)
    assert "no se pudo publicar la revocacion" in caplog.text


# --- 6.3 Bloqueo ------------------------------------------------------------------

def test_quinto_intento_bloquea_revoca_y_envia_un_email(client, cliente_activo, db_session, enviador, redis_test):
    refresh = login(client).json()["refresh_token"]
    enviador.enviados.clear()
    for i in range(1, 5):
        assert login(client, password="incorrecta-1234").status_code == 401
        assert _estado(db_session).intentos_fallidos == i
    assert enviador.enviados == []

    assert login(client, password="incorrecta-1234").status_code == 401
    estado = _estado(db_session)
    assert (estado.estado, estado.motivo_bloqueo) == ("bloqueada", "intentos_fallidos")

    [email] = enviador.enviados
    assert "bloqueó" in email.asunto and "/restablecer?token=" in email.cuerpo
    user_id = db_session.scalar(select(Usuario.id))
    assert redis_test.get(f"revocado:{user_id}") is not None
    assert client.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401
    # Con la contraseña correcta ahora se informa el bloqueo.
    assert login(client).json()["codigo"] == "cuenta_bloqueada"


def test_login_exitoso_reinicia_el_contador(client, cliente_activo, db_session):
    for _ in range(3):
        login(client, password="incorrecta-1234")
    assert login(client).status_code == 200
    assert _estado(db_session).intentos_fallidos == 0


def test_intentos_sobre_cuenta_ya_bloqueada_no_reenvian_email(client, cliente_activo, db_session, enviador):
    for _ in range(5):
        login(client, password="incorrecta-1234")
    for _ in range(3):
        login(client, password="incorrecta-1234")
    assert len(enviador.enviados) == 2  # verificacion del registro + un solo email de bloqueo


@pytest.mark.concurrencia
def test_intentos_simultaneos_bloquean_una_sola_vez(db_concurrente):
    settings = get_settings()
    datos = dict(DATOS_REGISTRO)
    email, password = datos.pop("email"), datos.pop("password")
    with Session(db_concurrente) as s:
        servicio.registrar_cliente(s, settings, servicio.Efectos(), email, password, **datos)
        s.execute(text("UPDATE users SET estado = 'activa', intentos_fallidos = 3"))
        s.commit()

    barrera = threading.Barrier(4)
    efectos = [servicio.Efectos() for _ in range(4)]

    def intentar(i):
        with Session(db_concurrente) as s:
            barrera.wait()
            with pytest.raises(servicio.CredencialesInvalidas):
                servicio.login(s, settings, efectos[i], email, "incorrecta-1234")

    hilos = [threading.Thread(target=intentar, args=(i,)) for i in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    with db_concurrente.connect() as c:
        fila = c.execute(text("SELECT estado, intentos_fallidos FROM users")).one()
    assert fila.estado == "bloqueada"
    emails = [e for ef in efectos for e in ef.emails]
    assert len(emails) == 1 and "bloqueó" in emails[0].asunto
    assert sum(len(ef.revocaciones) for ef in efectos) == 1


def test_el_email_de_bloqueo_se_envia_despues_de_responder(client, cliente_activo, enviador, monkeypatch):
    """BackgroundTasks: la respuesta no espera al SMTP."""
    lento = []

    def enviar_lento(email):
        time.sleep(0.01)
        lento.append(email)

    monkeypatch.setattr(enviador, "enviar", enviar_lento)
    for _ in range(5):
        r = login(client, password="incorrecta-1234")
    assert r.status_code == 401
    assert len(lento) == 1


def test_activar_helper(db_session, client):
    client.post("/auth/registro", json=DATOS_REGISTRO)
    activar(db_session)
    assert _estado(db_session).estado == "activa"
