"""Logica de negocio de auth. Recibe una Session y no conoce HTTP."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import seguridad
from app.config import Settings
from app.models import ROL_ADMINISTRADOR, ROL_CLIENTE, RefreshToken, Usuario


class EmailDuplicado(Exception):
    pass


class CredencialesInvalidas(Exception):
    pass


class RefreshInvalido(Exception):
    pass


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str
    expires_in: int


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def crear_usuario(session: Session, email: str, password: str, rol: str) -> Usuario:
    """Crea el usuario con el rol indicado por el codigo (nunca por el cliente).
    El UNIQUE de la base resuelve los registros simultaneos del mismo email."""
    usuario = Usuario(
        email=normalizar_email(email),
        password_hash=seguridad.hashear_password(password),
        rol=rol,
    )
    session.add(usuario)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise EmailDuplicado(email) from error
    return usuario


def registrar_cliente(session: Session, email: str, password: str) -> Usuario:
    return crear_usuario(session, email, password, ROL_CLIENTE)


def login(session: Session, settings: Settings, email: str, password: str) -> Tokens:
    usuario = session.scalar(select(Usuario).where(Usuario.email == normalizar_email(email)))
    # Se verifica siempre (con un hash ficticio si no existe) para no revelar
    # por tiempo de respuesta si el email esta registrado.
    if not seguridad.verificar_password(usuario.password_hash if usuario else None, password):
        raise CredencialesInvalidas()
    tokens = _emitir_tokens(session, settings, usuario)
    session.commit()
    return tokens


def refrescar(session: Session, settings: Settings, refresh_token: str) -> Tokens:
    """Rotacion atomica: el UPDATE condicional marca el token como usado una
    sola vez. Dos refresh simultaneos con el mismo token -> solo uno gana."""
    fila = session.execute(
        text(
            "UPDATE refresh_tokens SET used_at = now() "
            "WHERE token_hash = :h AND used_at IS NULL AND expires_at > now() "
            "RETURNING user_id"
        ),
        {"h": seguridad.hash_refresh_token(refresh_token)},
    ).first()
    if fila is None:
        session.rollback()
        raise RefreshInvalido()
    usuario = session.get(Usuario, fila.user_id)  # rol actual del usuario
    tokens = _emitir_tokens(session, settings, usuario)
    session.commit()
    return tokens


def _emitir_tokens(session: Session, settings: Settings, usuario: Usuario) -> Tokens:
    refresh = seguridad.nuevo_refresh_token()
    session.execute(
        insert(RefreshToken).values(
            user_id=usuario.id,
            token_hash=seguridad.hash_refresh_token(refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_ttl_days),
        )
    )
    access = seguridad.emitir_access_token(
        usuario.id, usuario.rol, settings.jwt_secret, settings.jwt_access_ttl_minutes
    )
    return Tokens(access_token=access, refresh_token=refresh, expires_in=settings.jwt_access_ttl_minutes * 60)


def crear_admin_inicial(session: Session, email: str | None, password: str | None) -> None:
    """Idempotente: crea el admin si no existe; si existe, no lo toca."""
    if not email or not password:
        return
    session.execute(
        pg_insert(Usuario)
        .values(
            email=normalizar_email(email),
            password_hash=seguridad.hashear_password(password),
            rol=ROL_ADMINISTRADOR,
        )
        .on_conflict_do_nothing(index_elements=["email"])
    )
    session.commit()
