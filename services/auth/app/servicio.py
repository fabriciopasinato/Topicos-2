"""Logica de negocio de auth. Recibe una Session y no conoce HTTP.

Las acciones que deben ocurrir DESPUES del commit (enviar emails, publicar la
revocacion en Redis) no se ejecutan aca: se anotan en `Efectos` y las ejecuta
la capa HTTP. Asi un rollback nunca deja un email enviado ni una marca en Redis.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import contrasenias, correo, revocacion, seguridad, tokens_cuenta
from app.config import Settings
from app.correo import Email
from app.models import (
    ACTIVA, BLOQUEADA, MOTIVO_ADMIN, MOTIVO_INTENTOS, PENDIENTE_VERIFICACION, ROL_ADMINISTRADOR, ROL_CLIENTE,
    ROL_EVENT_OWNER,
    TOKEN_RESTABLECIMIENTO, TOKEN_VERIFICACION, RefreshToken, Usuario,
)

# --- Errores de negocio ------------------------------------------------------


class EmailDuplicado(Exception):
    pass


class DniDuplicado(Exception):
    pass


class CredencialesInvalidas(Exception):
    pass


class CuentaNoActiva(Exception):
    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo  # email_no_verificado | cuenta_bloqueada


class RefreshInvalido(Exception):
    pass


class TokenInvalido(Exception):
    pass


class ContraseniaInvalida(Exception):
    def __init__(self, motivos: list[str]):
        super().__init__("; ".join(motivos))
        self.motivos = motivos


class NoEncontrado(Exception):
    pass


# --- Resultados y efectos ---------------------------------------------------------


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass
class Efectos:
    """Acciones a ejecutar despues del commit."""

    emails: list[Email] = field(default_factory=list)
    revocaciones: list[int] = field(default_factory=list)  # user_ids


CAMPOS_PERFIL = (
    "nombre", "apellido", "fecha_nacimiento", "telefono",
    "calle", "numero", "piso_depto", "localidad", "provincia", "codigo_postal",
)


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def _validar_contrasenia(contrasenia: str, email: str) -> None:
    motivos = contrasenias.problemas(contrasenia, email)
    if motivos:
        raise ContraseniaInvalida(motivos)


def _bloquear_sesiones(session: Session, user_id: int, efectos: Efectos) -> None:
    revocacion.revocar_refresh_tokens(session, user_id)
    efectos.revocaciones.append(user_id)


def _enviar_restablecimiento(session, settings, usuario, plantilla, efectos) -> None:
    token = tokens_cuenta.emitir(
        session, usuario.id, TOKEN_RESTABLECIMIENTO, timedelta(minutes=settings.restablecimiento_ttl_minutos)
    )
    efectos.emails.append(plantilla(settings, usuario.email, usuario.nombre, token))


# --- Alta de cuentas -----------------------------------------------------------------


def crear_usuario(session: Session, email: str, password: str, rol: str, **datos) -> Usuario:
    """Crea el usuario con el rol indicado por el codigo (nunca por el cliente).
    Los UNIQUE de la base resuelven los altas simultaneas del mismo email o DNI."""
    usuario = Usuario(
        email=normalizar_email(email), password_hash=seguridad.hashear_password(password), rol=rol, **datos
    )
    session.add(usuario)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        restriccion = getattr(getattr(error.orig, "diag", None), "constraint_name", "") or ""
        if "dni" in restriccion:
            raise DniDuplicado() from error
        raise EmailDuplicado(email) from error
    return usuario


def crear_event_owner(session: Session, email: str, password: str) -> Usuario:
    _validar_contrasenia(password, email)
    usuario = crear_usuario(session, email, password, ROL_EVENT_OWNER, estado=ACTIVA)
    session.commit()
    return usuario


def registrar_cliente(session: Session, settings: Settings, efectos: Efectos, email: str, password: str,
                      **datos) -> Usuario:
    _validar_contrasenia(password, email)
    usuario = crear_usuario(session, email, password, ROL_CLIENTE, estado=PENDIENTE_VERIFICACION, **datos)
    token = tokens_cuenta.emitir(
        session, usuario.id, TOKEN_VERIFICACION, timedelta(hours=settings.verificacion_ttl_horas)
    )
    session.commit()
    efectos.emails.append(correo.verificacion(settings, usuario.email, usuario.nombre, token))
    return usuario


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
            estado=ACTIVA,
        )
        .on_conflict_do_nothing(index_elements=["email"])
    )
    session.commit()


# --- Verificacion de email ---------------------------------------------------


def verificar_email(session: Session, token: str) -> None:
    user_id = tokens_cuenta.consumir(session, token, TOKEN_VERIFICACION)
    if user_id is None:
        session.rollback()
        raise TokenInvalido()
    session.execute(
        text("UPDATE users SET estado = 'activa' WHERE id = :u AND estado = 'pendiente_verificacion'"),
        {"u": user_id},
    )
    session.commit()


def reenviar_verificacion(session: Session, settings: Settings, efectos: Efectos, email: str) -> None:
    """Siempre "exito" hacia afuera: solo envia si la cuenta esta pendiente."""
    usuario = session.scalar(select(Usuario).where(Usuario.email == normalizar_email(email)))
    if usuario is None or usuario.estado != PENDIENTE_VERIFICACION:
        return
    token = tokens_cuenta.emitir(
        session, usuario.id, TOKEN_VERIFICACION, timedelta(hours=settings.verificacion_ttl_horas)
    )
    session.commit()
    efectos.emails.append(correo.verificacion(settings, usuario.email, usuario.nombre, token))


# --- Login y tokens ----------------------------------------------------------------


def login(session: Session, settings: Settings, efectos: Efectos, email: str, password: str) -> Tokens:
    usuario = session.scalar(select(Usuario).where(Usuario.email == normalizar_email(email)))
    # Se verifica siempre (con un hash ficticio si no existe) para no revelar
    # por tiempo de respuesta si el email esta registrado.
    correcta = seguridad.verificar_password(usuario.password_hash if usuario else None, password)

    if not correcta:
        if usuario is not None and usuario.estado == ACTIVA:
            _registrar_intento_fallido(session, settings, efectos, usuario)
        raise CredencialesInvalidas()  # mismo error para cualquier caso: no revela el estado

    if usuario.estado == PENDIENTE_VERIFICACION:
        raise CuentaNoActiva("email_no_verificado")
    if usuario.estado == BLOQUEADA:
        raise CuentaNoActiva("cuenta_bloqueada")

    session.execute(
        text("UPDATE users SET intentos_fallidos = 0, last_login_at = now() WHERE id = :u"), {"u": usuario.id}
    )
    tokens = _emitir_tokens(session, settings, usuario)
    session.commit()
    return tokens


def _registrar_intento_fallido(session, settings, efectos, usuario) -> None:
    """Conteo y bloqueo en un solo UPDATE atomico. Con intentos simultaneos,
    PostgreSQL serializa los UPDATE sobre la fila: solo el que llega al maximo
    dispara el bloqueo (y un unico email)."""
    fila = session.execute(
        text(
            "UPDATE users SET intentos_fallidos = intentos_fallidos + 1, "
            "  estado = CASE WHEN intentos_fallidos + 1 >= :max THEN 'bloqueada' ELSE estado END, "
            "  motivo_bloqueo = CASE WHEN intentos_fallidos + 1 >= :max THEN :motivo ELSE motivo_bloqueo END "
            "WHERE id = :u AND estado = 'activa' RETURNING intentos_fallidos"
        ),
        {"u": usuario.id, "max": settings.intentos_maximos, "motivo": MOTIVO_INTENTOS},
    ).first()
    if fila is not None and fila.intentos_fallidos == settings.intentos_maximos:
        _bloquear_sesiones(session, usuario.id, efectos)
        _enviar_restablecimiento(session, settings, usuario, correo.bloqueo, efectos)
    session.commit()


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
    usuario = session.get(Usuario, fila.user_id) if fila else None
    if usuario is None or usuario.estado != ACTIVA:
        session.rollback()
        raise RefreshInvalido()
    tokens = _emitir_tokens(session, settings, usuario)  # con el rol actual
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


# --- Recuperacion y restablecimiento ------------------------------------------------


def solicitar_restablecimiento(session: Session, settings: Settings, efectos: Efectos, email: str) -> None:
    """Siempre "exito" hacia afuera: solo envia si la cuenta existe."""
    usuario = session.scalar(select(Usuario).where(Usuario.email == normalizar_email(email)))
    if usuario is None:
        return
    _enviar_restablecimiento(session, settings, usuario, correo.restablecimiento, efectos)
    session.commit()


def restablecer_contrasenia(session: Session, efectos: Efectos, token: str, nueva: str) -> None:
    user_id = tokens_cuenta.vigente(session, token, TOKEN_RESTABLECIMIENTO)
    if user_id is None:
        raise TokenInvalido()
    usuario = session.get(Usuario, user_id)
    _validar_contrasenia(nueva, usuario.email)  # si es invalida, el token no se gasta

    if tokens_cuenta.consumir(session, token, TOKEN_RESTABLECIMIENTO) is None:
        session.rollback()  # otro uso simultaneo del mismo token gano
        raise TokenInvalido()
    session.execute(
        text(
            "UPDATE users SET password_hash = :h, estado = 'activa', motivo_bloqueo = NULL, "
            "intentos_fallidos = 0 WHERE id = :u"
        ),
        {"h": seguridad.hashear_password(nueva), "u": user_id},
    )
    _bloquear_sesiones(session, user_id, efectos)
    session.commit()


# --- Perfil ----------------------------------------------------------------------------


def obtener(session: Session, user_id: int) -> Usuario:
    usuario = session.get(Usuario, user_id)
    if usuario is None:
        raise NoEncontrado()
    return usuario


def editar_perfil(session: Session, user_id: int, cambios: dict) -> Usuario:
    usuario = obtener(session, user_id)
    for campo, valor in cambios.items():
        if campo in CAMPOS_PERFIL:  # email, dni, rol y estado no se editan aca
            setattr(usuario, campo, valor)
    session.commit()
    session.refresh(usuario)  # trae el updated_at que puso el trigger
    return usuario


def cambiar_contrasenia(session: Session, settings: Settings, efectos: Efectos, user_id: int,
                        actual: str, nueva: str) -> Tokens:
    usuario = obtener(session, user_id)
    if not seguridad.verificar_password(usuario.password_hash, actual):
        raise CredencialesInvalidas()
    _validar_contrasenia(nueva, usuario.email)
    usuario.password_hash = seguridad.hashear_password(nueva)
    _bloquear_sesiones(session, user_id, efectos)
    tokens = _emitir_tokens(session, settings, usuario)  # la sesion actual sigue
    session.commit()
    return tokens


# --- Administracion ------------------------------------------------------------------


def listar_cuentas(session: Session, q: str | None, rol: str | None, estado: str | None,
                   pagina: int, tamanio: int) -> tuple[list[Usuario], int]:
    consulta = select(Usuario)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(
            or_(
                Usuario.email.ilike(patron),
                func.unaccent(Usuario.apellido).ilike(func.unaccent(patron)),
                Usuario.dni.like(f"{q.strip()}%"),
            )
        )
    if rol:
        consulta = consulta.where(Usuario.rol == rol)
    if estado:
        consulta = consulta.where(Usuario.estado == estado)
    total = session.scalar(select(func.count()).select_from(consulta.subquery()))
    items = session.scalars(
        consulta.order_by(Usuario.id).offset((pagina - 1) * tamanio).limit(tamanio)
    ).all()
    return list(items), total


def admin_restablecer(session: Session, settings: Settings, efectos: Efectos, user_id: int) -> None:
    usuario = obtener(session, user_id)
    session.execute(
        text("UPDATE users SET estado = 'bloqueada', motivo_bloqueo = :m WHERE id = :u"),
        {"m": MOTIVO_ADMIN, "u": user_id},
    )
    _bloquear_sesiones(session, user_id, efectos)
    _enviar_restablecimiento(session, settings, usuario, correo.restablecimiento_admin, efectos)
    session.commit()
