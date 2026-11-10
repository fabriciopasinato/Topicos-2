"""Envio de emails por SMTP (design, decisiones 6 y 7).

En desarrollo el SMTP es el contenedor mailpit (no entrega nada). En
produccion se cambian las variables SMTP_* por las de un proveedor.
Los emails nunca contienen contrasenias: solo links de un solo uso.
"""

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import quote

from app.config import Settings, get_settings

log = logging.getLogger("auth.correo")


@dataclass(frozen=True)
class Email:
    destinatario: str
    asunto: str
    cuerpo: str


class EnviadorEmail(Protocol):
    def enviar(self, email: Email) -> None: ...


class EnviadorSMTP:
    def __init__(self, settings: Settings):
        self.s = settings

    def enviar(self, email: Email) -> None:
        mensaje = EmailMessage()
        mensaje["From"] = self.s.email_from
        mensaje["To"] = email.destinatario
        mensaje["Subject"] = email.asunto
        mensaje.set_content(email.cuerpo)
        try:
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=10) as smtp:
                if self.s.smtp_tls:
                    smtp.starttls()
                if self.s.smtp_user:
                    smtp.login(self.s.smtp_user, self.s.smtp_password or "")
                smtp.send_message(mensaje)
        except (OSError, smtplib.SMTPException) as error:
            # Se envia en segundo plano: el usuario puede pedir un reenvio.
            log.error("no se pudo enviar el email '%s' a %s: %s", email.asunto, email.destinatario, error)


class EnviadorFalso:
    """Para tests: acumula los emails en lugar de enviarlos."""

    def __init__(self):
        self.enviados: list[Email] = []

    def enviar(self, email: Email) -> None:
        self.enviados.append(email)


def get_enviador() -> EnviadorEmail:
    return EnviadorSMTP(get_settings())


# --- Plantillas -------------------------------------------------------------

def _link(settings: Settings, ruta: str, token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/{ruta}?token={quote(token)}"


def _saludo(nombre: str | None) -> str:
    return f"Hola {nombre}," if nombre else "Hola,"


def verificacion(settings: Settings, destinatario: str, nombre: str | None, token: str) -> Email:
    return Email(
        destinatario,
        "Verificá tu cuenta en Ticketera",
        f"{_saludo(nombre)}\n\nPara activar tu cuenta entrá a este link "
        f"(vence en {settings.verificacion_ttl_horas} horas):\n\n{_link(settings, 'verificar', token)}\n\n"
        "Si no creaste una cuenta, ignorá este email.\n",
    )


def restablecimiento(settings: Settings, destinatario: str, nombre: str | None, token: str) -> Email:
    return Email(
        destinatario,
        "Restablecé tu contraseña de Ticketera",
        f"{_saludo(nombre)}\n\nPediste restablecer tu contraseña. Creá una nueva desde este link "
        f"(vence en {settings.restablecimiento_ttl_minutos} minutos y sirve una sola vez):\n\n"
        f"{_link(settings, 'restablecer', token)}\n\nSi no lo pediste, ignorá este email: tu contraseña no cambió.\n",
    )


def bloqueo(settings: Settings, destinatario: str, nombre: str | None, token: str) -> Email:
    return Email(
        destinatario,
        "Tu cuenta de Ticketera se bloqueó",
        f"{_saludo(nombre)}\n\nTu cuenta se bloqueó por varios intentos de ingreso con una contraseña "
        "incorrecta. Para desbloquearla, creá una contraseña nueva desde este link "
        f"(vence en {settings.restablecimiento_ttl_minutos} minutos):\n\n"
        f"{_link(settings, 'restablecer', token)}\n\nSi no fuiste vos, te recomendamos elegir una contraseña distinta.\n",
    )


def restablecimiento_admin(settings: Settings, destinatario: str, nombre: str | None, token: str) -> Email:
    return Email(
        destinatario,
        "Un administrador restableció tu contraseña de Ticketera",
        f"{_saludo(nombre)}\n\nUn administrador restableció la contraseña de tu cuenta. Para volver a "
        "ingresar, creá una contraseña nueva desde este link "
        f"(vence en {settings.restablecimiento_ttl_minutos} minutos):\n\n"
        f"{_link(settings, 'restablecer', token)}\n",
    )
