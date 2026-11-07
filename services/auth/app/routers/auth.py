from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import servicio
from app.config import get_settings
from app.db import get_session
from app.identidad import Identidad, requiere_rol
from app.models import ROL_ADMINISTRADOR, ROL_EVENT_OWNER

router = APIRouter(prefix="/auth")

_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class Credenciales(BaseModel):
    # Cualquier otro campo (por ejemplo "rol") se ignora.
    email: str = Field(pattern=_EMAIL, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class UsuarioOut(BaseModel):
    id: int
    email: str
    rol: str


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


def _usuario_out(usuario) -> UsuarioOut:
    return UsuarioOut(id=usuario.id, email=usuario.email, rol=usuario.rol)


@router.post("/registro", status_code=status.HTTP_201_CREATED, response_model=UsuarioOut)
def registro(datos: Credenciales, session: Session = Depends(get_session)):
    try:
        return _usuario_out(servicio.registrar_cliente(session, datos.email, datos.password))
    except servicio.EmailDuplicado:
        raise HTTPException(status_code=409, detail="el email ya esta registrado")


@router.post("/login", response_model=TokensOut)
def login(datos: LoginIn, session: Session = Depends(get_session)):
    try:
        return TokensOut(**vars(servicio.login(session, get_settings(), datos.email, datos.password)))
    except servicio.CredencialesInvalidas:
        raise HTTPException(status_code=401, detail="email o contrasenia incorrectos")


@router.post("/refresh", response_model=TokensOut)
def refresh(datos: RefreshIn, session: Session = Depends(get_session)):
    try:
        return TokensOut(**vars(servicio.refrescar(session, get_settings(), datos.refresh_token)))
    except servicio.RefreshInvalido:
        raise HTTPException(status_code=401, detail="refresh token invalido, usado o expirado")


@router.post("/event-owners", status_code=status.HTTP_201_CREATED, response_model=UsuarioOut)
def crear_event_owner(
    datos: Credenciales,
    session: Session = Depends(get_session),
    _: Identidad = Depends(requiere_rol(ROL_ADMINISTRADOR)),
):
    try:
        return _usuario_out(servicio.crear_usuario(session, datos.email, datos.password, ROL_EVENT_OWNER))
    except servicio.EmailDuplicado:
        raise HTTPException(status_code=409, detail="el email ya esta registrado")
