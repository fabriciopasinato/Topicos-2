"""Identidad del usuario, tal como la envia el gateway (X-User-Id / X-User-Role).

El servicio solo es alcanzable desde la red interna y el gateway descarta esos
headers si vienen del cliente, por eso aca se confia en ellos.
"""

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException


@dataclass(frozen=True)
class Identidad:
    user_id: int
    rol: str


def identidad_actual(
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> Identidad:
    if not x_user_id or not x_user_role:
        raise HTTPException(status_code=401, detail="se requiere autenticacion")
    return Identidad(user_id=int(x_user_id), rol=x_user_role)


def requiere_rol(*roles: str):
    def _verificar(identidad: Identidad = Depends(identidad_actual)) -> Identidad:
        if identidad.rol not in roles:
            raise HTTPException(status_code=403, detail="operacion no permitida para este rol")
        return identidad

    return _verificar
