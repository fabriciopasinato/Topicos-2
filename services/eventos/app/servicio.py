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
    """Sin espacios al principio ni al final y con los internos colapsados.
    Es como se guarda y se muestra el nombre."""
    return " ".join(nombre.split())


def normalizar_nombre(nombre: str) -> str:
    """Clave de unicidad: el nombre limpio y sin distinguir mayusculas.
    " los  PIOJOS " y "Los Piojos" tienen la misma clave."""
    return limpiar_nombre(nombre).casefold()


def buscar_o_crear(session: Session, modelo: type[Organizador] | type[Participante], nombre: str):
    """Devuelve el organizador o participante con ese nombre (sin distinguir
    mayusculas ni espacios) y lo crea si no existe.

    INSERT ... ON CONFLICT DO NOTHING sobre la clave unica: si otra transaccion
    esta insertando la misma clave, este INSERT espera a que termine; si ella
    confirma, no inserta nada y el SELECT siguiente ve su fila. Asi dos altas
    simultaneas del mismo nombre terminan en una sola fila, sin capturar
    errores de integridad. No hace commit: es parte de la transaccion de quien llama.
    """
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
    """Reloj de la base, el mismo que usa ventas para cerrar la venta: asi los
    dos servicios coinciden en cuando empezo un evento."""
    return session.scalar(select(func.now()))


def estado_de(evento: Evento, momento: datetime) -> str:
    """Estado informado: el guardado, salvo un evento publicado cuya fecha de
    inicio ya llego, que se informa `finalizado` (no se guarda)."""
    if evento.estado == PUBLICADO and evento.fecha <= momento:
        return FINALIZADO
    return evento.estado


class Accion(StrEnum):
    """Lo que se le puede hacer a un evento. Que se permite en cada estado lo
    decide una sola tabla: ACCIONES_PERMITIDAS."""

    EDITAR = "editar"
    CAMBIAR_RECINTO = "cambiar el recinto de"
    MODIFICAR_ZONAS = "modificar las zonas de"
    PUBLICAR = "publicar"
    REPROGRAMAR = "reprogramar"
    CANCELAR = "cancelar"
    BORRAR = "borrar"


# Matriz de que se puede hacer en cada estado (el informado, con finalizado
# calculado). Cambiar una regla es cambiar una celda.
ACCIONES_PERMITIDAS: dict[str, frozenset[Accion]] = {
    BORRADOR: frozenset(Accion),  # todo
    PUBLICADO: frozenset({Accion.EDITAR, Accion.REPROGRAMAR, Accion.CANCELAR}),
    FINALIZADO: frozenset(),
    CANCELADO: frozenset(),
}


def exigir_permitido(evento: Evento, accion: Accion, momento: datetime) -> None:
    """Conflicto (409) si la accion no esta permitida en el estado del evento.
    Las repeticiones idempotentes (publicar un publicado, cancelar un
    cancelado) las resuelve cada operacion antes de llamar a esta funcion."""
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
    """Publicados (incluidos los finalizados) y cancelados que llegaron a
    publicarse: los ve cualquiera, por ejemplo desde "Mis compras". Borradores
    y cancelados sin publicar: solo su owner y los administradores."""
    return evento.estado == PUBLICADO or (evento.estado == CANCELADO and evento.publicado_at is not None)


def obtener_visible(session: Session, evento_id: int, identidad: Identidad | None) -> Evento:
    """Para quien no puede verlo, el evento 'no existe' (404)."""
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
    """Eventos publicados que todavia no empezaron (reloj de la base),
    filtrables por tipo y rango de fechas de inicio, ordenados por fecha.
    Cancelados y finalizados no se listan."""
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
    """Busca o crea cada participante; un mismo participante indicado dos
    veces (aunque se escriba distinto) queda una sola vez."""
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
        session.rollback()  # descarta organizadores o participantes ya creados
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
    """Edita datos descriptivos de un evento en borrador o publicado vigente.
    No avisa a ventas: ninguno de estos datos esta replicado alla."""
    evento = obtener_gestionable(session, evento_id, identidad, bloquear=True)
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)  # solo lo que se mando
    try:
        momento = ahora(session)
        exigir_permitido(evento, Accion.EDITAR, momento)
        if _hay_cancelacion_pendiente(session, evento_id):
            raise Conflicto("el evento tiene una cancelacion pendiente")
        if "recinto_id" in cambios and cambios["recinto_id"] != evento.recinto_id:
            exigir_permitido(evento, Accion.CAMBIAR_RECINTO, momento)
            evento.recinto_id = _exigir_recinto(session, cambios["recinto_id"])

        for campo in ("nombre", "descripcion"):  # asignacion directa
            if campo in cambios:
                setattr(evento, campo, cambios[campo])
        # Los que validan o buscan algo, uno por uno:
        if "tipo" in cambios:
            evento.tipo = _exigir_tipo(session, cambios["tipo"])
        if "organizador" in cambios:
            evento.organizador = buscar_o_crear(session, Organizador, cambios["organizador"])
        if "participantes" in cambios:
            evento.participantes = _participantes(session, cambios["participantes"])
    except (Conflicto, Invalido):
        session.rollback()  # libera el lock y descarta lo creado a medias
        raise
    session.commit()
    return evento


def borrar_evento(session: Session, evento_id: int, identidad: Identidad) -> None:
    """Solo borradores. Se borran sus sectores, zonas, asientos y su relacion
    con los participantes; organizadores y participantes quedan (pueden estar
    en otros eventos)."""
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
    """Lo que ventas necesita para vender: zonas, asientos, precios y la fecha
    de inicio (con la que ventas cierra la venta sin consultar a eventos)."""
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


# --- Outbox hacia ventas: que significa cada tipo de operacion -------------------

@dataclass(frozen=True)
class Efecto:
    """Lo que significa un tipo de operacion, en los dos servicios. Definirlo
    en un solo lugar evita que el envio y la aplicacion se desincronicen, y
    que un tipo nuevo caiga en un caso por defecto equivocado."""

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
    """Como termino una cancelacion o reprogramacion."""

    APLICADO = "aplicado"    # ya rige en eventos (y en ventas, si estaba publicado) -> 200
    PENDIENTE = "pendiente"  # guardada; falta que ventas confirme (eventos-cron) -> 202


# --- Outbox hacia ventas: aplicar una operacion confirmada ------------------------

def aplicar(session: Session, operacion_id: int) -> None:
    """Aplica en eventos una operacion que ventas ya confirmo, y la marca
    confirmada. La usan el envio inmediato y eventos-cron.

    Idempotente y tolerante al desorden: aplica solo si la version es mayor a
    la ultima aplicada, y nunca sobre un evento cancelado (la cancelacion es
    final). Una operacion vieja o repetida se marca confirmada sin efecto.

    Orden de locks: primero la operacion y despues el evento, igual que el cron.
    Con el mismo orden en todos lados, dos confirmaciones simultaneas de la
    misma operacion se esperan en lugar de bloquearse mutuamente (deadlock).
    """
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


# --- Outbox hacia ventas: registrar, enviar y reintentar --------------------------

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
    """TX1 del outbox: con el evento bloqueado, asigna la proxima version y
    guarda la intencion. Desde el commit, la operacion ya no se pierde: si el
    envio falla o el proceso se cae, eventos-cron la reintenta."""
    evento.version += 1
    op = OperacionVentas(evento_id=evento.id, tipo=tipo, version=evento.version, fecha=fecha)
    session.add(op)
    session.commit()
    return op.id


def registrar_fallo(session: Session, operacion_id: int, error: Exception) -> None:
    """Posterga el proximo intento con espera exponencial (5, 10, 20, 40, 60, 60... s)."""
    session.execute(
        update(OperacionVentas)
        .where(OperacionVentas.id == operacion_id)
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
    """Envia la operacion a ventas (sin locks tomados durante el HTTP). Si
    ventas confirma, la aplica en eventos; si no, registra el fallo."""
    op = session.get(OperacionVentas, operacion_id)
    evento_id, version, cambios = op.evento_id, op.version, EFECTOS[op.tipo].cambios_para_ventas(op)
    session.rollback()  # no retener nada mientras se espera a ventas
    try:
        ventas.actualizar_evento(evento_id, version, **cambios)
    except VentasNoDisponible as error:
        registrar_fallo(session, operacion_id, error)
        return Resultado.PENDIENTE
    aplicar(session, operacion_id)
    return Resultado.APLICADO


def cancelar(session: Session, evento_id: int, identidad: Identidad, ventas: ClienteVentas) -> Resultado:
    """Cancela un evento.

    Borrador: se cancela al instante (ventas no tiene su inventario).
    Publicado: outbox; queda `publicado` hasta que ventas confirme.
    Ya cancelado, o con una cancelacion pendiente: no registra nada nuevo.
    """
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
    """Cambia la fecha de inicio.

    Borrador: se aplica al instante. Publicado: outbox; el evento conserva la
    fecha anterior hasta que ventas confirme la nueva.
    """
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
