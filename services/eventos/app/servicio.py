"""Logica de negocio de eventos. Recibe una Session y no conoce HTTP."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.cliente_ventas import ClienteVentas, VentasNoDisponible
from app.identidad import Identidad
from app.models import (
    BORRADOR, CANCELADO, FINALIZADO, GENERAL, NUMERADA, PUBLICADO, Asiento, EstadoOperacion, Evento, OperacionVentas,
    Organizador, Participante, Recinto, Sector, TipoEvento, TipoOperacion, Zona,
)
from app.schemas import EventoIn, EventoPatch, ZonaIn


class NoEncontrado(Exception):
    pass


class Prohibido(Exception):
    pass


class Conflicto(Exception):
    pass


class Invalido(Exception):
    pass


LARGO_MAXIMO_NOMBRE = 200


def limpiar_nombre(nombre: str) -> str:
    return " ".join(nombre.split())


def normalizar_nombre(nombre: str) -> str:
    return limpiar_nombre(nombre).casefold()


def buscar_o_crear(session: Session, modelo: type[Organizador] | type[Participante], nombre: str):
    """ON CONFLICT DO NOTHING + SELECT: dos altas simultaneas del mismo nombre
    terminan en una sola fila. No hace commit."""
    limpio = limpiar_nombre(nombre)
    if not limpio:
        raise Invalido("el nombre no puede estar vacio")
    if len(limpio) > LARGO_MAXIMO_NOMBRE:
        raise Invalido(f"el nombre admite como maximo {LARGO_MAXIMO_NOMBRE} caracteres")
    clave = limpio.casefold()

    nuevo_id = session.execute(
        pg_insert(modelo).values(nombre=limpio, clave=clave)
        .on_conflict_do_nothing(index_elements=["clave"])
        .returning(modelo.id)
    ).scalar()
    if nuevo_id is None:
        nuevo_id = session.scalar(select(modelo.id).where(modelo.clave == clave))
    return session.get(modelo, nuevo_id)


def ahora(session: Session) -> datetime:
    """Reloj de la base: el mismo que usa ventas para cerrar la venta."""
    return session.scalar(select(func.now()))


def estado_de(evento: Evento, momento: datetime) -> str:
    if evento.estado == PUBLICADO and evento.fecha <= momento:
        return FINALIZADO
    return evento.estado


class Accion(StrEnum):
    EDITAR = "editar"
    CAMBIAR_RECINTO = "cambiar el recinto de"
    MODIFICAR_ZONAS = "modificar las zonas de"
    PUBLICAR = "publicar"
    REPROGRAMAR = "reprogramar"
    CANCELAR = "cancelar"
    BORRAR = "borrar"


ACCIONES_PERMITIDAS: dict[str, frozenset[Accion]] = {
    BORRADOR: frozenset(Accion),
    PUBLICADO: frozenset({Accion.EDITAR, Accion.REPROGRAMAR, Accion.CANCELAR}),
    FINALIZADO: frozenset(),
    CANCELADO: frozenset(),
}


def exigir_permitido(evento: Evento, accion: Accion, momento: datetime) -> None:
    """Las repeticiones idempotentes (publicar un publicado, cancelar un
    cancelado) se resuelven antes de llamar a esta funcion."""
    estado = estado_de(evento, momento)
    if accion not in ACCIONES_PERMITIDAS[estado]:
        raise Conflicto(f"no se puede {accion} un evento {estado}")


def listar_tipos(session: Session) -> list[TipoEvento]:
    return list(session.scalars(select(TipoEvento).order_by(TipoEvento.nombre)))


def _cargar_clasificacion():
    return (
        selectinload(Evento.recinto),
        selectinload(Evento.organizador),
        selectinload(Evento.participantes),
    )


def _cargar_detalle():
    return (
        *_cargar_clasificacion(),
        selectinload(Evento.sectores).selectinload(Sector.zonas).selectinload(Zona.asientos),
    )


def puede_gestionar(evento: Evento, identidad: Identidad | None) -> bool:
    return identidad is not None and (identidad.es_admin or evento.owner_id == identidad.user_id)


def es_publico(evento: Evento) -> bool:
    return evento.estado == PUBLICADO or (evento.estado == CANCELADO and evento.publicado_at is not None)


def obtener_visible(session: Session, evento_id: int, identidad: Identidad | None) -> Evento:
    evento = session.scalar(select(Evento).where(Evento.id == evento_id).options(*_cargar_detalle()))
    if evento is None or (not es_publico(evento) and not puede_gestionar(evento, identidad)):
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


def listar_cartelera(session: Session, tipo: str | None = None,
                     desde: datetime | None = None, hasta: datetime | None = None) -> list[Evento]:
    if tipo is not None:
        _exigir_tipo(session, tipo)
    if desde is not None and hasta is not None and desde > hasta:
        raise Invalido("el inicio del rango no puede ser posterior a su fin")
    consulta = select(Evento).where(Evento.estado == PUBLICADO, Evento.fecha > func.now())
    if tipo is not None:
        consulta = consulta.where(Evento.tipo == tipo)
    if desde is not None:
        consulta = consulta.where(Evento.fecha >= desde)
    if hasta is not None:
        consulta = consulta.where(Evento.fecha <= hasta)
    return list(session.scalars(consulta.options(*_cargar_clasificacion()).order_by(Evento.fecha)))


def listar_propios(session: Session, identidad: Identidad) -> list[Evento]:
    consulta = select(Evento).options(*_cargar_clasificacion()).order_by(Evento.id)
    if not identidad.es_admin:
        consulta = consulta.where(Evento.owner_id == identidad.user_id)
    return list(session.scalars(consulta))


def crear_recinto(session: Session, nombre: str, direccion: str) -> Recinto:
    recinto = Recinto(nombre=nombre, direccion=direccion)
    session.add(recinto)
    session.commit()
    return recinto


def _exigir_tipo(session: Session, codigo: str) -> str:
    if session.get(TipoEvento, codigo) is None:
        raise Invalido(f"el tipo de evento '{codigo}' no existe")
    return codigo


def _exigir_recinto(session: Session, recinto_id: int) -> int:
    if session.get(Recinto, recinto_id) is None:
        raise Invalido("el recinto no existe")
    return recinto_id


def _participantes(session: Session, nombres: list[str]) -> list[Participante]:
    unicos: dict[int, Participante] = {}
    for nombre in nombres:
        participante = buscar_o_crear(session, Participante, nombre)
        unicos.setdefault(participante.id, participante)
    return list(unicos.values())


def crear_evento(session: Session, datos: EventoIn, identidad: Identidad) -> Evento:
    if session.get(Recinto, datos.recinto_id) is None:
        raise Invalido("el recinto no existe")
    try:
        _exigir_tipo(session, datos.tipo)
        organizador = buscar_o_crear(session, Organizador, datos.organizador)
        participantes = _participantes(session, datos.participantes)
    except Invalido:
        session.rollback()
        raise
    evento = Evento(
        owner_id=identidad.user_id, nombre=datos.nombre, fecha=datos.fecha,
        recinto_id=datos.recinto_id, estado=BORRADOR, tipo=datos.tipo,
        descripcion=datos.descripcion, organizador=organizador, participantes=participantes,
    )
    session.add(evento)
    session.commit()
    return evento


def editar_evento(session: Session, evento_id: int, datos: EventoPatch, identidad: Identidad) -> Evento:
    """No avisa a ventas: ninguno de estos datos esta replicado alla."""
    evento = obtener_gestionable(session, evento_id, identidad, bloquear=True)
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    try:
        momento = ahora(session)
        exigir_permitido(evento, Accion.EDITAR, momento)
        if _hay_cancelacion_pendiente(session, evento_id):
            raise Conflicto("el evento tiene una cancelacion pendiente")
        if "recinto_id" in cambios and cambios["recinto_id"] != evento.recinto_id:
            exigir_permitido(evento, Accion.CAMBIAR_RECINTO, momento)
            evento.recinto_id = _exigir_recinto(session, cambios["recinto_id"])

        for campo in ("nombre", "descripcion"):
            if campo in cambios:
                setattr(evento, campo, cambios[campo])
        if "tipo" in cambios:
            evento.tipo = _exigir_tipo(session, cambios["tipo"])
        if "organizador" in cambios:
            evento.organizador = buscar_o_crear(session, Organizador, cambios["organizador"])
        if "participantes" in cambios:
            evento.participantes = _participantes(session, cambios["participantes"])
    except (Conflicto, Invalido):
        session.rollback()
        raise
    session.commit()
    return evento


def borrar_evento(session: Session, evento_id: int, identidad: Identidad) -> None:
    """Organizadores y participantes no se borran: pueden estar en otros eventos."""
    evento = obtener_gestionable(session, evento_id, identidad, bloquear=True)
    try:
        exigir_permitido(evento, Accion.BORRAR, ahora(session))
    except Conflicto:
        session.rollback()
        raise
    session.delete(evento)
    session.commit()


def _exigir_zonas_modificables(session: Session, evento: Evento) -> None:
    exigir_permitido(evento, Accion.MODIFICAR_ZONAS, ahora(session))


def crear_sector(session: Session, evento_id: int, nombre: str, identidad: Identidad) -> Sector:
    evento = obtener_gestionable(session, evento_id, identidad)
    _exigir_zonas_modificables(session, evento)
    sector = Sector(evento_id=evento.id, nombre=nombre)
    session.add(sector)
    session.commit()
    return sector


def crear_zona(session: Session, evento_id: int, sector_id: int, datos: ZonaIn, identidad: Identidad) -> Zona:
    evento = obtener_gestionable(session, evento_id, identidad)
    _exigir_zonas_modificables(session, evento)
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
    _exigir_zonas_modificables(session, evento)
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
    return {"evento_id": evento.id, "zonas": zonas, "fecha_inicio": evento.fecha.isoformat()}


def publicar(session: Session, evento_id: int, identidad: Identidad, ventas: ClienteVentas) -> Evento:
    """Envia el inventario a ventas y recien con su confirmacion marca el
    evento como publicado. Si ventas no responde, el evento sigue en borrador.
    El lock de la fila evita dos publicaciones simultaneas del mismo evento."""
    evento = obtener_gestionable(session, evento_id, identidad, bloquear=True)
    if evento.estado == PUBLICADO:
        session.rollback()
        return obtener_visible(session, evento_id, identidad)
    try:
        exigir_permitido(evento, Accion.PUBLICAR, ahora(session))
    except Conflicto:
        session.rollback()
        raise
    if evento.fecha <= ahora(session):
        session.rollback()
        raise Invalido("no se puede publicar un evento cuya fecha de inicio ya paso")

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
    evento.publicado_at = func.now()
    session.commit()
    return evento


# --- Outbox hacia ventas ------------------------------------------------------------

@dataclass(frozen=True)
class Efecto:
    cambios_para_ventas: Callable[[OperacionVentas], dict]  # kwargs de ClienteVentas.actualizar_evento
    aplicar_en_eventos: Callable[[Evento, OperacionVentas], None]


def _reprogramar_evento(evento: Evento, op: OperacionVentas) -> None:
    evento.fecha = op.fecha


def _cancelar_evento(evento: Evento, op: OperacionVentas) -> None:
    evento.estado = CANCELADO


EFECTOS: dict[TipoOperacion, Efecto] = {
    TipoOperacion.REPROGRAMAR: Efecto(
        cambios_para_ventas=lambda op: {"fecha_inicio": op.fecha},
        aplicar_en_eventos=_reprogramar_evento,
    ),
    TipoOperacion.CANCELAR: Efecto(
        cambios_para_ventas=lambda op: {"cancelado": True},
        aplicar_en_eventos=_cancelar_evento,
    ),
}


class Resultado(StrEnum):
    APLICADO = "aplicado"
    PENDIENTE = "pendiente"  # falta que ventas confirme; la reintenta eventos-cron


def aplicar(session: Session, operacion_id: int) -> None:
    """Orden de locks: primero la operacion y despues el evento, igual que el
    cron. Invertirlo puede producir un deadlock entre los dos."""
    op = session.scalar(select(OperacionVentas).where(OperacionVentas.id == operacion_id).with_for_update())
    if op is None or op.estado == EstadoOperacion.CONFIRMADA:
        session.rollback()
        return
    evento = session.scalar(
        select(Evento).where(Evento.id == op.evento_id).with_for_update().execution_options(populate_existing=True)
    )
    if op.version > evento.version_aplicada and evento.estado != CANCELADO:
        EFECTOS[op.tipo].aplicar_en_eventos(evento, op)
        evento.version_aplicada = op.version
    op.estado = EstadoOperacion.CONFIRMADA
    op.confirmada_at = func.now()
    session.commit()


ESPERA_BASE_SEGUNDOS = 5
ESPERA_MAXIMA_SEGUNDOS = 60


def operaciones_pendientes(session: Session, evento_id: int) -> list[OperacionVentas]:
    return list(session.scalars(
        select(OperacionVentas)
        .where(OperacionVentas.evento_id == evento_id, OperacionVentas.estado == EstadoOperacion.PENDIENTE)
        .order_by(OperacionVentas.id)
    ))


def _hay_cancelacion_pendiente(session: Session, evento_id: int) -> bool:
    return session.scalar(
        select(func.count()).select_from(OperacionVentas).where(
            OperacionVentas.evento_id == evento_id,
            OperacionVentas.tipo == TipoOperacion.CANCELAR,
            OperacionVentas.estado == EstadoOperacion.PENDIENTE,
        )
    ) > 0


def _registrar_operacion(session: Session, evento: Evento, tipo: TipoOperacion,
                         fecha: datetime | None = None) -> int:
    """Requiere el evento bloqueado (la version no puede repetirse)."""
    evento.version += 1
    op = OperacionVentas(evento_id=evento.id, tipo=tipo, version=evento.version, fecha=fecha)
    session.add(op)
    session.commit()
    return op.id


def registrar_fallo(session: Session, operacion_id: int, error: Exception) -> None:
    session.execute(
        update(OperacionVentas)
        # Si otro envio simultaneo ya la confirmo, este fallo no la toca.
        .where(OperacionVentas.id == operacion_id, OperacionVentas.estado == EstadoOperacion.PENDIENTE)
        .values(
            intentos=OperacionVentas.intentos + 1,
            ultimo_error=str(error)[:500],
            proximo_intento_at=func.now() + func.make_interval(
                0, 0, 0, 0, 0, 0,
                func.least(ESPERA_MAXIMA_SEGUNDOS, ESPERA_BASE_SEGUNDOS * func.power(2, OperacionVentas.intentos)),
            ),
        )
    )
    session.commit()


def enviar(session: Session, operacion_id: int, ventas: ClienteVentas) -> Resultado:
    op = session.get(OperacionVentas, operacion_id)
    evento_id, version, cambios = op.evento_id, op.version, EFECTOS[op.tipo].cambios_para_ventas(op)
    session.rollback()  # sin locks tomados mientras se espera a ventas
    try:
        ventas.actualizar_evento(evento_id, version, **cambios)
    except VentasNoDisponible as error:
        registrar_fallo(session, operacion_id, error)
        return Resultado.PENDIENTE
    aplicar(session, operacion_id)
    return Resultado.APLICADO


def cancelar(session: Session, evento_id: int, identidad: Identidad, ventas: ClienteVentas) -> Resultado:
    evento = obtener_gestionable(session, evento_id, identidad, bloquear=True)
    if evento.estado == CANCELADO:
        session.rollback()
        return Resultado.APLICADO
    if _hay_cancelacion_pendiente(session, evento_id):
        session.rollback()
        return Resultado.PENDIENTE
    try:
        exigir_permitido(evento, Accion.CANCELAR, ahora(session))
    except Conflicto:
        session.rollback()
        raise
    if evento.estado == BORRADOR:
        evento.estado = CANCELADO
        session.commit()
        return Resultado.APLICADO
    operacion_id = _registrar_operacion(session, evento, TipoOperacion.CANCELAR)
    return enviar(session, operacion_id, ventas)


def reprogramar(session: Session, evento_id: int, identidad: Identidad, ventas: ClienteVentas,
                fecha: datetime) -> Resultado:
    evento = obtener_gestionable(session, evento_id, identidad, bloquear=True)
    try:
        momento = ahora(session)
        exigir_permitido(evento, Accion.REPROGRAMAR, momento)
        if _hay_cancelacion_pendiente(session, evento_id):
            raise Conflicto("el evento tiene una cancelacion pendiente")
        if fecha <= momento:
            raise Invalido("la nueva fecha tiene que ser futura")
    except (Conflicto, Invalido):
        session.rollback()
        raise
    if evento.estado == BORRADOR:
        evento.fecha = fecha
        session.commit()
        return Resultado.APLICADO
    operacion_id = _registrar_operacion(session, evento, TipoOperacion.REPROGRAMAR, fecha)
    return enviar(session, operacion_id, ventas)
