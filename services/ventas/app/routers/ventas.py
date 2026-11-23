from contextlib import contextmanager
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app import servicio
from app.config import get_settings
from app.db import get_session
from app.identidad import Identidad, requiere_rol

router = APIRouter()
cliente = requiere_rol("cliente")
admin = requiere_rol("administrador")
cliente_o_admin = requiere_rol("cliente", "administrador")


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
    fecha_inicio: datetime | None = None


class ActualizacionEventoIn(BaseModel):
    version: int = Field(gt=0)
    fecha_inicio: datetime | None = None
    cancelado: bool = False

    @model_validator(mode="after")
    def _algun_cambio(self):
        if self.fecha_inicio is None and not self.cancelado:
            raise ValueError("indicar fecha_inicio o cancelado")
        return self


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


class DevolucionIn(BaseModel):
    orden_item_id: int = Field(gt=0)
    motivo: str | None = Field(default=None, max_length=500)


class ResolucionDevolucionIn(BaseModel):
    nota: str | None = Field(default=None, max_length=500)


class DevolucionOut(BaseModel):
    id: int
    orden_item_id: int
    orden_id: int
    ticket_id: int
    user_id: int
    evento_id: int
    zona_id: int
    tipo_zona: str
    fila: str | None
    numero: int | None
    precio: float
    estado: str
    motivo: str | None
    nota_resolucion: str | None
    resuelto_por: int | None
    resuelto_at: datetime | None
    created_at: datetime
    evento_fecha_inicio: datetime | None
    evento_cancelado: bool


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
    except servicio.EventoNoALaVenta:
        raise HTTPException(status_code=409, detail="el evento fue cancelado o ya comenzo")
    except servicio.DevolucionYaExiste:
        raise HTTPException(status_code=409, detail="el ticket ya tiene una devolucion pendiente o aprobada")
    except servicio.DevolucionYaResuelta:
        raise HTTPException(status_code=409, detail="la devolucion ya fue resuelta")
    except servicio.EventoFinalizado:
        raise HTTPException(status_code=409, detail="el evento ya comenzo")
    except servicio.TicketNoLiberable:
        raise HTTPException(status_code=409, detail="el ticket ya no esta vendido en esa orden")


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


@router.put("/internal/eventos/{evento_id}")
def actualizar_evento(evento_id: int, datos: ActualizacionEventoIn, session: Session = Depends(get_session)):
    """200 tambien si lo ignora por version: ventas ya esta al dia."""
    with _errores():
        aplicado = servicio.actualizar_evento(
            session, evento_id, datos.version, datos.fecha_inicio, datos.cancelado,
        )
    return {"evento_id": evento_id, "version": datos.version, "aplicado": aplicado}


# --- Publico (via gateway) ------------------------------------------------------

@router.get("/ventas/eventos/{evento_id}/disponibilidad")
def disponibilidad(evento_id: int, session: Session = Depends(get_session)):
    with _errores():
        return servicio.disponibilidad(session, evento_id)


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


@router.post("/ventas/devoluciones", status_code=status.HTTP_201_CREATED, response_model=DevolucionOut)
def solicitar_devolucion(
    datos: DevolucionIn,
    session: Session = Depends(get_session),
    identidad: Identidad = Depends(cliente),
):
    with _errores():
        return servicio.solicitar_devolucion(session, identidad.user_id, datos.orden_item_id, datos.motivo)


@router.get("/ventas/devoluciones", response_model=list[DevolucionOut])
def listar_devoluciones(
    estado: str | None = None,
    session: Session = Depends(get_session),
    identidad: Identidad = Depends(cliente_o_admin),
):
    with _errores():
        return servicio.listar_devoluciones(session, identidad.user_id, identidad.rol, estado)


@router.post("/ventas/devoluciones/{devolucion_id}/aprobar", response_model=DevolucionOut)
def aprobar_devolucion(
    devolucion_id: int,
    datos: ResolucionDevolucionIn | None = None,
    session: Session = Depends(get_session),
    identidad: Identidad = Depends(admin),
):
    with _errores():
        nota = datos.nota if datos is not None else None
        return servicio.aprobar_devolucion(session, devolucion_id, identidad.user_id, nota)


@router.post("/ventas/devoluciones/{devolucion_id}/rechazar", response_model=DevolucionOut)
def rechazar_devolucion(
    devolucion_id: int,
    datos: ResolucionDevolucionIn | None = None,
    session: Session = Depends(get_session),
    identidad: Identidad = Depends(admin),
):
    with _errores():
        nota = datos.nota if datos is not None else None
        return servicio.rechazar_devolucion(session, devolucion_id, identidad.user_id, nota)
