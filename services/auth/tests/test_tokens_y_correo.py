"""4.1 Tokens de cuenta y 4.2 envio de emails."""

import socket
import threading
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import correo, tokens_cuenta
from app.config import Settings, get_settings
from app.models import TOKEN_RESTABLECIMIENTO, TOKEN_VERIFICACION


def _usuario(session) -> int:
    return session.execute(
        text("INSERT INTO users (email, password_hash, rol) VALUES ('t@x.com', 'h', 'cliente') RETURNING id")
    ).scalar()


# --- 4.1 Tokens de cuenta ----------------------------------------------------------

def test_token_vigente_se_consume_una_sola_vez(db_session):
    uid = _usuario(db_session)
    token = tokens_cuenta.emitir(db_session, uid, TOKEN_RESTABLECIMIENTO, timedelta(minutes=30))
    assert tokens_cuenta.vigente(db_session, token, TOKEN_RESTABLECIMIENTO) == uid
    assert tokens_cuenta.consumir(db_session, token, TOKEN_RESTABLECIMIENTO) == uid
    assert tokens_cuenta.consumir(db_session, token, TOKEN_RESTABLECIMIENTO) is None


def test_solo_se_guarda_el_hash(db_session):
    uid = _usuario(db_session)
    token = tokens_cuenta.emitir(db_session, uid, TOKEN_VERIFICACION, timedelta(hours=24))
    guardado = db_session.execute(text("SELECT token_hash FROM tokens_cuenta")).scalar()
    assert guardado != token and len(guardado) == 64


def test_token_vencido_no_sirve(db_session):
    uid = _usuario(db_session)
    token = tokens_cuenta.emitir(db_session, uid, TOKEN_RESTABLECIMIENTO, timedelta(minutes=30))
    db_session.execute(text("UPDATE tokens_cuenta SET expires_at = now() - interval '1 second'"))
    assert tokens_cuenta.consumir(db_session, token, TOKEN_RESTABLECIMIENTO) is None


def test_tipo_equivocado_no_sirve(db_session):
    uid = _usuario(db_session)
    token = tokens_cuenta.emitir(db_session, uid, TOKEN_VERIFICACION, timedelta(hours=24))
    assert tokens_cuenta.consumir(db_session, token, TOKEN_RESTABLECIMIENTO) is None


def test_solo_sirve_el_ultimo_emitido(db_session):
    uid = _usuario(db_session)
    viejo = tokens_cuenta.emitir(db_session, uid, TOKEN_RESTABLECIMIENTO, timedelta(minutes=30))
    nuevo = tokens_cuenta.emitir(db_session, uid, TOKEN_RESTABLECIMIENTO, timedelta(minutes=30))
    assert tokens_cuenta.consumir(db_session, viejo, TOKEN_RESTABLECIMIENTO) is None
    assert tokens_cuenta.consumir(db_session, nuevo, TOKEN_RESTABLECIMIENTO) == uid


def test_vigencias_configuradas(db_session):
    uid = _usuario(db_session)
    tokens_cuenta.emitir(db_session, uid, TOKEN_VERIFICACION, timedelta(hours=24))
    horas = db_session.execute(
        text("SELECT extract(epoch FROM expires_at - now()) / 3600 FROM tokens_cuenta")).scalar()
    assert 23.9 < float(horas) <= 24


@pytest.mark.concurrencia
def test_dos_consumos_simultaneos_del_mismo_token(db_concurrente):
    with Session(db_concurrente) as s:
        uid = _usuario(s)
        token = tokens_cuenta.emitir(s, uid, TOKEN_RESTABLECIMIENTO, timedelta(minutes=30))
        s.commit()

    barrera = threading.Barrier(2)
    resultados = []

    def consumir():
        with Session(db_concurrente) as s:
            barrera.wait()
            resultados.append(tokens_cuenta.consumir(s, token, TOKEN_RESTABLECIMIENTO))
            s.commit()

    hilos = [threading.Thread(target=consumir) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(resultados, key=lambda r: r is None) == [uid, None]


# --- 4.2 Emails --------------------------------------------------------------------

PLANTILLAS = [
    (correo.verificacion, "/verificar?token="),
    (correo.restablecimiento, "/restablecer?token="),
    (correo.bloqueo, "/restablecer?token="),
    (correo.restablecimiento_admin, "/restablecer?token="),
]


@pytest.mark.parametrize("plantilla,ruta", PLANTILLAS)
def test_cada_plantilla_tiene_el_link_y_ninguna_contrasenia(plantilla, ruta):
    s = get_settings()
    email = plantilla(s, "ana@example.com", "Ana", "TOKEN123")
    assert email.destinatario == "ana@example.com"
    assert f"{s.frontend_url}{ruta}TOKEN123" in email.cuerpo
    assert "Hola Ana" in email.cuerpo
    assert "contraseña:" not in email.cuerpo.lower() and "password" not in email.cuerpo.lower()


class ServidorSMTPDePrueba:
    """SMTP minimo en un hilo: acepta un mensaje y lo guarda."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.puerto = self.sock.getsockname()[1]
        self.mensaje = None
        self.hilo = threading.Thread(target=self._atender, daemon=True)
        self.hilo.start()

    def _atender(self):
        conn, _ = self.sock.accept()
        archivo = conn.makefile("rwb")

        def responder(linea):
            archivo.write(linea.encode() + b"\r\n")
            archivo.flush()

        responder("220 prueba")
        datos = []
        en_datos = False
        for crudo in archivo:
            linea = crudo.decode().rstrip("\r\n")
            if en_datos:
                if linea == ".":
                    en_datos = False
                    self.mensaje = "\n".join(datos)
                    responder("250 OK")
                else:
                    datos.append(linea)
            elif linea.upper().startswith(("EHLO", "HELO")):
                responder("250 prueba")
            elif linea.upper() == "DATA":
                en_datos = True
                responder("354 dale")
            elif linea.upper() == "QUIT":
                responder("221 chau")
                break
            else:
                responder("250 OK")
        conn.close()
        self.sock.close()


def test_el_enviador_smtp_entrega_al_servidor():
    servidor = ServidorSMTPDePrueba()
    settings = Settings(database_url="x", jwt_secret="x", smtp_host="127.0.0.1", smtp_port=servidor.puerto)
    email = correo.verificacion(settings, "ana@example.com", "Ana", "TOKEN123")
    correo.EnviadorSMTP(settings).enviar(email)
    servidor.hilo.join(timeout=5)
    assert "To: ana@example.com" in servidor.mensaje
    assert "From: no-reply@ticketera.local" in servidor.mensaje
    assert "TOKEN123" in servidor.mensaje


def test_smtp_caido_no_lanza_y_queda_en_el_log(caplog):
    settings = Settings(database_url="x", jwt_secret="x", smtp_host="127.0.0.1", smtp_port=1)
    correo.EnviadorSMTP(settings).enviar(correo.Email("a@b.c", "asunto", "cuerpo"))
    assert "no se pudo enviar el email" in caplog.text
