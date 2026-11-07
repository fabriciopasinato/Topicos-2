"""Logica de negocio de eventos. Recibe una Session y no conoce HTTP."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.cliente_ventas import ClienteVentas, VentasNoDisponible
from app.identidad import Identidad
from app.models import BORRADOR, GENERAL, NUMERADA, PUBLICADO, Asiento, Evento, Recinto, Sector, Zona
from app.schemas import EventoIn, EventoPatch, ZonaIn


class NoEncontrado(Exception):
    pass


class Prohibido(Exception):
    pass


class Conflicto(Exception):
    pass


class Invalido(Exception):
    pass


def _cargar_detalle():
    return (
        selectinload(Evento.recinto),
        selectinload(Evento.sectores).selectinload(Sector.zonas).selectinload(Zona.asientos),
    )


def puede_gestionar(evento: Evento, identidad: Identidad | None) -> bool:
    return identidad is not None and (identidad.es_admin or evento.owner_id == identidad.user_id)


def obtener_visible(session: Session, evento_id: int, identidad: Identidad | None) -> Evento:
    """Publicados: para todos. Borradores: solo para su owner y los admin
    (para el resto, el evento 'no existe')."""
    evento = session.scalar(select(Evento).where(Evento.id == evento_id).options(*_cargar_detalle()))
    if evento is None or (evento.estado != PUBLICADO and not puede_gestionar(evento, identidad)):
        raise NoEncontrado()
    return evento


def obtener_gestionable(session: Session, evento_id: int, identidad: Identidad, bloquear: bool = False) -> Evento:
    consulta = select(Evento).where(Evento.id == evento_id)
    if bloquear:
        consulta = consulta.with_for_update()
    evento = session.scalar(consulta)
    if evento is None:
        raise NoEncontrado()
    if not puede_gestionar(evento, identidad):
        raise Prohibido()
    return evento


def listar_publicados(session: Session) -> list[Evento]:
    return list(
        session.scalars(
            select(Evento).where(Evento.estado == PUBLICADO).options(selectinload(Evento.recinto)).order_by(Evento.fecha)
        )
    )


def listar_propios(session: Session, identidad: Identidad) -> list[Evento]:
    consulta = select(Evento).options(selectinload(Evento.recinto)).order_by(Evento.id)
    if not identidad.es_admin:
        consulta = consulta.where(Evento.owner_id == identidad.user_id)
    return list(session.scalars(consulta))


def crear_recinto(session: Session, nombre: str, direccion: str) -> Recinto:
    recinto = Recinto(nombre=nombre, direccion=direccion)
    session.add(recinto)
    session.commit()
    return recinto


def crear_evento(session: Session, datos: EventoIn, identidad: Identidad) -> Evento:
    if session.get(Recinto, datos.recinto_id) is None:
        raise Invalido("el recinto no existe")
    evento = Evento(
        owner_id=identidad.user_id, nombre=datos.nombre, fecha=datos.fecha,
        recinto_id=datos.recinto_id, estado=BORRADOR,
    )
    session.add(evento)
    session.commit()
    return evento


def editar_evento(session: Session, evento_id: int, datos: EventoPatch, identidad: Identidad) -> Evento:
    evento = obtener_gestionable(session, evento_id, identidad)
    if datos.nombre is not None:
        evento.nombre = datos.nombre
    if datos.fecha is not None:
        evento.fecha = datos.fecha
    session.commit()
    return evento


def _exigir_borrador(evento: Evento) -> None:
    if evento.estado != BORRADOR:
        raise Conflicto("las zonas de un evento publicado no se pueden modificar")


def crear_sector(session: Session, evento_id: int, nombre: str, identidad: Identidad) -> Sector:
    evento = obtener_gestionable(session, evento_id, identidad)
    _exigir_borrador(evento)
    sector = Sector(evento_id=evento.id, nombre=nombre)
    session.add(sector)
    session.commit()
    return sector


def crear_zona(session: Session, evento_id: int, sector_id: int, datos: ZonaIn, identidad: Identidad) -> Zona:
    evento = obtener_gestionable(session, evento_id, identidad)
    _exigir_borrador(evento)
    sector = session.get(Sector, sector_id)
    if sector is None or sector.evento_id != evento.id:
        raise NoEncontrado()

    if datos.tipo == NUMERADA:
        asientos = [
            Asiento(fila=fila, numero=n)
            for fila in datos.filas
            for n in range(1, datos.asientos_por_fila + 1)
        ]
        capacidad = len(asientos)
    else:
        asientos = []
        capacidad = datos.capacidad

    zona = Zona(
        sector_id=sector.id, nombre=datos.nombre, tipo=datos.tipo,
        capacidad=capacidad, precio=datos.precio, asientos=asientos,
    )
    session.add(zona)
    session.commit()
    return zona


def borrar_zona(session: Session, evento_id: int, zona_id: int, identidad: Identidad) -> None:
    evento = obtener_gestionable(session, evento_id, identidad)
    zona = session.get(Zona, zona_id)
    if zona is None or zona.sector.evento_id != evento.id:
        raise NoEncontrado()
    _exigir_borrador(evento)
    session.delete(zona)
    session.commit()


def inventario_de(evento: Evento) -> dict:
    """Lo que ventas necesita para vender: zonas, asientos y precios."""
    zonas = []
    for sector in evento.sectores:
        for zona in sector.zonas:
            item = {"zona_id": zona.id, "tipo": zona.tipo, "precio": str(zona.precio)}
            if zona.tipo == NUMERADA:
                item["asientos"] = [{"fila": a.fila, "numero": a.numero} for a in zona.asientos]
            else:
                item["capacidad"] = zona.capacidad
            zonas.append(item)
    return {"evento_id": evento.id, "zonas": zonas}


def publicar(session: Session, evento_id: int, identidad: Identidad, ventas: ClienteVentas) -> Evento:
    """Envia el inventario a ventas y recien con su confirmacion marca el
    evento como publicado. Si ventas no responde, el evento sigue en borrador.
    El lock de la fila evita dos publicaciones simultaneas del mismo evento."""
    evento = obtener_gestionable(session, evento_id, identidad, bloquear=True)
    if evento.estado == PUBLICADO:
        session.rollback()
        return obtener_visible(session, evento_id, identidad)

    evento = session.scalar(
        select(Evento).where(Evento.id == evento_id).options(*_cargar_detalle()).execution_options(populate_existing=True)
    )
    inventario = inventario_de(evento)
    if not inventario["zonas"]:
        session.rollback()
        raise Invalido("el evento no tiene zonas")

    try:
        ventas.enviar_inventario(inventario)
    except VentasNoDisponible:
        session.rollback()
        raise

    evento.estado = PUBLICADO
    session.commit()
    return evento
