from contextlib import contextmanager

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import revocacion, servicio
from app.config import get_settings
from app.correo import EnviadorEmail, get_enviador
from app.db import get_session
from app.identidad import Identidad, identidad_actual, requiere_rol
from app.models import ESTADOS, ROL_ADMINISTRADOR, ROLES
from app.schemas import (
    CambioContraseniaIn, CuentaAdminOut, EmailIn, EventOwnerIn, LoginIn, PaginaCuentas, PerfilOut, PerfilPatch,
    RefreshIn, RegistroIn, RestablecerIn, TokenIn, TokensOut, UsuarioOut,
)

router = APIRouter(prefix="/auth")
solo_admin = requiere_rol(ROL_ADMINISTRADOR)


class Ejecutor:
    """Ejecuta los efectos posteriores al commit: publica las revocaciones en
    Redis y programa los emails en segundo plano (despues de responder)."""

    def __init__(
        self,
        background: BackgroundTasks,
        enviador: EnviadorEmail = Depends(get_enviador),
        redis=Depends(revocacion.get_redis),
    ):
        self.background = background
        self.enviador = enviador
        self.redis = redis
        self.efectos = servicio.Efectos()

    def aplicar(self) -> None:
        ttl = get_settings().jwt_access_ttl_minutes * 60
        for user_id in self.efectos.revocaciones:
            revocacion.publicar(self.redis, user_id, ttl)
        for email in self.efectos.emails:
            self.background.add_task(self.enviador.enviar, email)


def _error_campo(campo: str, motivos: list[str]) -> HTTPException:
    """422 con el mismo formato que la validacion de FastAPI, para que el
    frontend muestre el error junto al campo."""
    return HTTPException(
        status_code=422, detail=[{"loc": ["body", campo], "msg": m, "type": "value_error"} for m in motivos]
    )


@contextmanager
def _errores(campo_contrasenia: str = "password"):
    try:
        yield
    except servicio.EmailDuplicado:
        raise HTTPException(status_code=409, detail="El email ya está registrado.")
    except servicio.DniDuplicado:
        raise HTTPException(status_code=409, detail="El DNI ya está registrado.")
    except servicio.ContraseniaInvalida as e:
        raise _error_campo(campo_contrasenia, e.motivos)
    except servicio.TokenInvalido:
        raise HTTPException(status_code=400, detail="El link no es válido o ya venció.")
    except servicio.NoEncontrado:
        raise HTTPException(status_code=404, detail="No encontrado.")


# --- Registro y verificacion ------------------------------------------------------


@router.post("/registro", status_code=status.HTTP_201_CREATED, response_model=UsuarioOut)
def registro(datos: RegistroIn, session: Session = Depends(get_session), ejecutor: Ejecutor = Depends()):
    perfil = datos.model_dump(exclude={"email", "password"})
    with _errores():
        usuario = servicio.registrar_cliente(
            session, get_settings(), ejecutor.efectos, datos.email, datos.password, **perfil
        )
    ejecutor.aplicar()
    return UsuarioOut(id=usuario.id, email=usuario.email, rol=usuario.rol)


@router.post("/verificar-email")
def verificar_email(datos: TokenIn, session: Session = Depends(get_session)):
    with _errores():
        servicio.verificar_email(session, datos.token)
    return {"detail": "Cuenta verificada."}


@router.post("/reenviar-verificacion", status_code=status.HTTP_202_ACCEPTED)
def reenviar_verificacion(datos: EmailIn, session: Session = Depends(get_session), ejecutor: Ejecutor = Depends()):
    servicio.reenviar_verificacion(session, get_settings(), ejecutor.efectos, datos.email)
    ejecutor.aplicar()
    return {"detail": "Si la cuenta existe y falta verificarla, te enviamos un email."}


# --- Login y tokens -------------------------------------------------------------


@router.post("/login", response_model=TokensOut)
def login(datos: LoginIn, session: Session = Depends(get_session), ejecutor: Ejecutor = Depends()):
    try:
        tokens = servicio.login(session, get_settings(), ejecutor.efectos, datos.email, datos.password)
    except servicio.CredencialesInvalidas:
        ejecutor.aplicar()  # puede haber un bloqueo recien producido
        return JSONResponse(
            status_code=401,
            content={"detail": "Email o contraseña incorrectos.", "codigo": "credenciales_invalidas"},
        )
    except servicio.CuentaNoActiva as e:
        mensajes = {
            "email_no_verificado": "Tenés que verificar tu email antes de ingresar.",
            "cuenta_bloqueada": "Tu cuenta está bloqueada. Revisá tu email para restablecer la contraseña.",
        }
        return JSONResponse(status_code=403, content={"detail": mensajes[e.codigo], "codigo": e.codigo})
    return TokensOut(**vars(tokens))


@router.post("/refresh", response_model=TokensOut)
def refresh(datos: RefreshIn, session: Session = Depends(get_session)):
    try:
        return TokensOut(**vars(servicio.refrescar(session, get_settings(), datos.refresh_token)))
    except servicio.RefreshInvalido:
        raise HTTPException(status_code=401, detail="refresh token invalido, usado o expirado")


# --- Recuperacion ------------------------------------------------------------------


@router.post("/olvide-contrasenia", status_code=status.HTTP_202_ACCEPTED)
def olvide_contrasenia(datos: EmailIn, session: Session = Depends(get_session), ejecutor: Ejecutor = Depends()):
    servicio.solicitar_restablecimiento(session, get_settings(), ejecutor.efectos, datos.email)
    ejecutor.aplicar()
    return {"detail": "Si el email está registrado, te enviamos un link para restablecer la contraseña."}


@router.post("/restablecer-contrasenia")
def restablecer_contrasenia(datos: RestablecerIn, session: Session = Depends(get_session),
                            ejecutor: Ejecutor = Depends()):
    with _errores("contrasenia"):
        servicio.restablecer_contrasenia(session, ejecutor.efectos, datos.token, datos.contrasenia)
    ejecutor.aplicar()
    return {"detail": "Contraseña actualizada. Ya podés ingresar."}


# --- Perfil -----------------------------------------------------------------------


@router.get("/perfil", response_model=PerfilOut)
def ver_perfil(session: Session = Depends(get_session), identidad: Identidad = Depends(identidad_actual)):
    with _errores():
        return PerfilOut.model_validate(servicio.obtener(session, identidad.user_id), from_attributes=True)


@router.patch("/perfil", response_model=PerfilOut)
def editar_perfil(datos: PerfilPatch, session: Session = Depends(get_session),
                  identidad: Identidad = Depends(identidad_actual)):
    with _errores():
        usuario = servicio.editar_perfil(session, identidad.user_id, datos.model_dump(exclude_unset=True))
    return PerfilOut.model_validate(usuario, from_attributes=True)


@router.post("/perfil/contrasenia", response_model=TokensOut)
def cambiar_contrasenia(datos: CambioContraseniaIn, session: Session = Depends(get_session),
                        identidad: Identidad = Depends(identidad_actual), ejecutor: Ejecutor = Depends()):
    try:
        with _errores("nueva"):
            tokens = servicio.cambiar_contrasenia(
                session, get_settings(), ejecutor.efectos, identidad.user_id, datos.actual, datos.nueva
            )
    except servicio.CredencialesInvalidas:
        raise HTTPException(status_code=401, detail="La contraseña actual no es correcta.")
    ejecutor.aplicar()
    return TokensOut(**vars(tokens))


# --- Administracion ----------------------------------------------------------------


@router.post("/event-owners", status_code=status.HTTP_201_CREATED, response_model=UsuarioOut)
def crear_event_owner(datos: EventOwnerIn, session: Session = Depends(get_session),
                      _: Identidad = Depends(solo_admin)):
    with _errores():
        usuario = servicio.crear_event_owner(session, datos.email, datos.password)
    return UsuarioOut(id=usuario.id, email=usuario.email, rol=usuario.rol)


@router.get("/admin/usuarios", response_model=PaginaCuentas)
def listar_cuentas(
    q: str | None = Query(default=None, max_length=100),
    rol: str | None = Query(default=None, enum=list(ROLES)),
    estado: str | None = Query(default=None, enum=list(ESTADOS)),
    pagina: int = Query(default=1, ge=1),
    tamanio: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    _: Identidad = Depends(solo_admin),
):
    items, total = servicio.listar_cuentas(session, q, rol, estado, pagina, tamanio)
    return PaginaCuentas(
        items=[CuentaAdminOut.model_validate(u, from_attributes=True) for u in items],
        total=total, pagina=pagina, tamanio=tamanio,
    )


@router.get("/admin/usuarios/{user_id}", response_model=CuentaAdminOut)
def detalle_cuenta(user_id: int, session: Session = Depends(get_session), _: Identidad = Depends(solo_admin)):
    with _errores():
        return CuentaAdminOut.model_validate(servicio.obtener(session, user_id), from_attributes=True)


@router.post("/admin/usuarios/{user_id}/restablecer-contrasenia", status_code=status.HTTP_202_ACCEPTED)
def admin_restablecer(user_id: int, session: Session = Depends(get_session), _: Identidad = Depends(solo_admin),
                      ejecutor: Ejecutor = Depends()):
    with _errores():
        servicio.admin_restablecer(session, get_settings(), ejecutor.efectos, user_id)
    ejecutor.aplicar()
    return {"detail": "Se envió al usuario un email para crear una contraseña nueva."}
