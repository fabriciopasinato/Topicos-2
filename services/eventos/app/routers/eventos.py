from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import servicio
from app.models import Recinto
from app.cliente_ventas import ClienteVentas, VentasNoDisponible, get_cliente_ventas
from app.db import get_session
from app.identidad import ROL_ADMINISTRADOR, ROL_EVENT_OWNER, Identidad, identidad_opcional, requiere_rol
from app.schemas import (
    EventoDetalle, EventoIn, EventoPatch, EventoResumen, RecintoIn, RecintoOut, SectorIn, SectorOut, TipoEventoOut,
    ZonaIn, ZonaOut,
)

router = APIRouter(prefix="/eventos")
gestor = requiere_rol(ROL_EVENT_OWNER, ROL_ADMINISTRADOR)


@contextmanager
def _errores():
    """Traduce los errores de negocio a codigos HTTP."""
    try:
        yield
    except servicio.NoEncontrado:
        raise HTTPException(status_code=404, detail="no encontrado")
    except servicio.Prohibido:
        raise HTTPException(status_code=403, detail="solo el owner del evento o un administrador")
    except servicio.Conflicto as e:
        raise HTTPException(status_code=409, detail=str(e))
    except servicio.Invalido as e:
        raise HTTPException(status_code=422, detail=str(e))
    except VentasNoDisponible:
        raise HTTPException(status_code=503, detail="ventas no disponible: el evento sigue en borrador")


def _detalle(session: Session, evento) -> EventoDetalle:
    """Detalle con el estado calculado (finalizado) segun el reloj de la base."""
    estado = servicio.estado_de(evento, servicio.ahora(session))
    return EventoDetalle.model_validate(evento, from_attributes=True).model_copy(update={"estado": estado})


def _resumenes(session: Session, eventos) -> list[EventoResumen]:
    momento = servicio.ahora(session)
    return [
        EventoResumen.model_validate(e, from_attributes=True).model_copy(update={"estado": servicio.estado_de(e, momento)})
        for e in eventos
    ]


# --- Recintos -------------------------------------------------------------
@router.get("/recintos", response_model=list[RecintoOut])
def listar_recintos(session: Session = Depends(get_session)):
    recintos = session.scalars(select(Recinto).order_by(Recinto.id))
    return [RecintoOut.model_validate(r, from_attributes=True) for r in recintos]


@router.post("/recintos", status_code=status.HTTP_201_CREATED, response_model=RecintoOut)
def crear_recinto(datos: RecintoIn, session: Session = Depends(get_session), _: Identidad = Depends(gestor)):
    return RecintoOut.model_validate(servicio.crear_recinto(session, datos.nombre, datos.direccion), from_attributes=True)


# --- Eventos --------------------------------------------------------------
@router.get("", response_model=list[EventoResumen])
def cartelera(session: Session = Depends(get_session)):
    return _resumenes(session, servicio.listar_publicados(session))


@router.get("/tipos", response_model=list[TipoEventoOut])
def tipos(session: Session = Depends(get_session)):
    """Catalogo de tipos de evento. Publico (GET /api/eventos/*)."""
    return [TipoEventoOut.model_validate(t, from_attributes=True) for t in servicio.listar_tipos(session)]


@router.get("/mios", response_model=list[EventoResumen])
def mis_eventos(session: Session = Depends(get_session), identidad: Identidad = Depends(gestor)):
    return _resumenes(session, servicio.listar_propios(session, identidad))


@router.get("/{evento_id}", response_model=EventoDetalle)
def detalle(evento_id: int, session: Session = Depends(get_session),
            identidad: Identidad | None = Depends(identidad_opcional)):
    with _errores():
        return _detalle(session, servicio.obtener_visible(session, evento_id, identidad))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=EventoDetalle)
def crear_evento(datos: EventoIn, session: Session = Depends(get_session), identidad: Identidad = Depends(gestor)):
    with _errores():
        evento = servicio.crear_evento(session, datos, identidad)
        return _detalle(session, servicio.obtener_visible(session, evento.id, identidad))


@router.patch("/{evento_id}", response_model=EventoDetalle)
def editar_evento(evento_id: int, datos: EventoPatch, session: Session = Depends(get_session),
                  identidad: Identidad = Depends(gestor)):
    with _errores():
        servicio.editar_evento(session, evento_id, datos, identidad)
        return _detalle(session, servicio.obtener_visible(session, evento_id, identidad))


@router.post("/{evento_id}/sectores", status_code=status.HTTP_201_CREATED, response_model=SectorOut)
def crear_sector(evento_id: int, datos: SectorIn, session: Session = Depends(get_session),
                 identidad: Identidad = Depends(gestor)):
    with _errores():
        sector = servicio.crear_sector(session, evento_id, datos.nombre, identidad)
        return SectorOut(id=sector.id, nombre=sector.nombre, zonas=[])


@router.post("/{evento_id}/sectores/{sector_id}/zonas", status_code=status.HTTP_201_CREATED, response_model=ZonaOut)
def crear_zona(evento_id: int, sector_id: int, datos: ZonaIn, session: Session = Depends(get_session),
               identidad: Identidad = Depends(gestor)):
    with _errores():
        zona = servicio.crear_zona(session, evento_id, sector_id, datos, identidad)
        return ZonaOut.model_validate(zona, from_attributes=True)


@router.delete("/{evento_id}/zonas/{zona_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_zona(evento_id: int, zona_id: int, session: Session = Depends(get_session),
                identidad: Identidad = Depends(gestor)):
    with _errores():
        servicio.borrar_zona(session, evento_id, zona_id, identidad)
    return Response(status_code=204)


@router.post("/{evento_id}/publicar", response_model=EventoDetalle)
def publicar(evento_id: int, session: Session = Depends(get_session), identidad: Identidad = Depends(gestor),
             ventas: ClienteVentas = Depends(get_cliente_ventas)):
    with _errores():
        return _detalle(session, servicio.publicar(session, evento_id, identidad, ventas))
