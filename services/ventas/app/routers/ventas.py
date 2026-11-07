from contextlib import contextmanager
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import servicio
from app.config import get_settings
from app.db import get_session
from app.identidad import Identidad, requiere_rol

router = APIRouter()
cliente = requiere_rol("cliente")


# --- Esquemas -------------------------------------------------------------------

class ZonaInventario(BaseModel):
    zona_id: int
    tipo: str = Field(pattern="^(numerada|general)$")
    precio: str
    asientos: list[dict] | None = None
    capacidad: int | None = Field(default=None, gt=0)


class InventarioIn(BaseModel):
    evento_id: int
    zonas: list[ZonaInventario]


class GeneralIn(BaseModel):
    zona_id: int
    cantidad: int = Field(gt=0)


class ReservaIn(BaseModel):
    evento_id: int
    asientos: list[int] = []  # ids de tickets numerados (de la disponibilidad)
    generales: list[GeneralIn] = []


class TicketOut(BaseModel):
    id: int
    zona_id: int
    tipo_zona: str
    fila: str | None
    numero: int | None
    precio: float


class ReservaOut(BaseModel):
    id: int
    evento_id: int
    estado: str  # activa | vencida | pagada | cancelada
    hasta: datetime
    total: float
    tickets: list[TicketOut]


class OrdenOut(BaseModel):
    id: int
    reserva_id: int
    total: float


@contextmanager
def _errores():
    try:
        yield
    except servicio.NoEncontrado:
        raise HTTPException(status_code=404, detail="no encontrado")
    except servicio.Invalido as e:
        raise HTTPException(status_code=422, detail=str(e))
    except servicio.ClaveReutilizada:
        raise HTTPException(status_code=422, detail="Idempotency-Key ya usada con otro contenido")
    except servicio.NoDisponible as e:
        raise HTTPException(status_code=409, detail=str(e))
    except servicio.ReservaNoVigente:
        raise HTTPException(status_code=409, detail="la reserva vencio o fue cancelada")
    except servicio.ReservaPagada:
        raise HTTPException(status_code=409, detail="la reserva ya fue pagada")


def _reserva_out(session: Session, reserva) -> ReservaOut:
    tickets = servicio.tickets_de_reserva(session, reserva.id)
    estado = reserva.estado
    if estado == "activa" and not servicio.reserva_vigente(session, reserva):
        estado = "vencida"
    return ReservaOut(
        id=reserva.id, evento_id=reserva.evento_id, estado=estado, hasta=reserva.hasta,
        total=float(sum(t.precio for t in tickets)),
        tickets=[TicketOut.model_validate(t, from_attributes=True) for t in tickets],
    )


# --- Interno (solo red interna; el gateway no lo expone) -------------------------

@router.post("/internal/inventario")
def recibir_inventario(datos: InventarioIn, session: Session = Depends(get_session)):
    creado = servicio.recibir_inventario(session, datos.model_dump())
    return {"evento_id": datos.evento_id, "creado": creado}


# --- Publico (via gateway) ------------------------------------------------------

@router.get("/ventas/eventos/{evento_id}/disponibilidad")
def disponibilidad(evento_id: int, session: Session = Depends(get_session)):
    with _errores():
        return {"evento_id": evento_id, "zonas": servicio.disponibilidad(session, evento_id)}


@router.post("/ventas/reservas", status_code=status.HTTP_201_CREATED, response_model=ReservaOut)
def reservar(
    datos: ReservaIn,
    session: Session = Depends(get_session),
    identidad: Identidad = Depends(cliente),
    idempotency_key: str | None = Header(default=None, max_length=255),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="falta el header Idempotency-Key")
    settings = get_settings()
    pedido = servicio.PedidoReserva(
        evento_id=datos.evento_id,
        asientos=tuple(datos.asientos),
        generales=tuple((g.zona_id, g.cantidad) for g in datos.generales),
    )
    with _errores():
        reserva = servicio.reservar(
            session, identidad.user_id, idempotency_key, pedido,
            settings.reserva_ttl_minutes, settings.reserva_max_tickets,
        )
        return _reserva_out(session, reserva)


@router.get("/ventas/reservas/{reserva_id}", response_model=ReservaOut)
def ver_reserva(reserva_id: int, session: Session = Depends(get_session), identidad: Identidad = Depends(cliente)):
    with _errores():
        return _reserva_out(session, servicio.obtener_reserva(session, reserva_id, identidad.user_id))


@router.post("/ventas/reservas/{reserva_id}/pago", status_code=status.HTTP_201_CREATED, response_model=OrdenOut)
def pagar(reserva_id: int, session: Session = Depends(get_session), identidad: Identidad = Depends(cliente)):
    with _errores():
        orden = servicio.pagar(session, reserva_id, identidad.user_id)
        return OrdenOut(id=orden.id, reserva_id=orden.reserva_id, total=float(orden.total))


@router.delete("/ventas/reservas/{reserva_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancelar(reserva_id: int, session: Session = Depends(get_session), identidad: Identidad = Depends(cliente)):
    with _errores():
        servicio.cancelar(session, reserva_id, identidad.user_id)
    return Response(status_code=204)


@router.get("/ventas/compras")
def compras(session: Session = Depends(get_session), identidad: Identidad = Depends(cliente)):
    return servicio.compras_de(session, identidad.user_id)
