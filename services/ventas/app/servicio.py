"""Logica de negocio de ventas. Recibe una Session y no conoce HTTP.

Garantia central: un ticket nunca se asigna a dos reservas vigentes ni se
vende dos veces. Se logra con UPDATE condicionales atomicos sobre la fila del
ticket dentro de una transaccion local de ventas_db (ver design.md, decision 11).

Vencimiento "perezoso": no hay proceso que libere reservas. Un ticket
reservado cuyo plazo ya paso se considera disponible en la propia condicion de
las consultas (DISPONIBLE_EFECTIVO). El reloj es siempre now() de PostgreSQL.
"""

import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ACTIVA, CANCELADA, DEVOLUCION_PENDIENTE, ESTADOS_DEVOLUCION, PAGADA,
    Devolucion, IdempotencyKey, InventarioEvento, Orden, OrdenItem, Reserva, Ticket,
)

# Unica definicion de "disponible": la usan las reservas y la disponibilidad.
DISPONIBLE_EFECTIVO = (
    "(t.estado = 'disponible' OR (t.estado = 'reservado' AND t.reservado_hasta < now()))"
)


class NoEncontrado(Exception):
    pass


class Invalido(Exception):
    pass


class ClaveReutilizada(Exception):
    """Misma Idempotency-Key con otro contenido."""


@dataclass
class NoDisponible(Exception):
    asientos: list[str] = field(default_factory=list)
    zonas: list[int] = field(default_factory=list)

    def __str__(self) -> str:
        partes = []
        if self.asientos:
            partes.append("asientos no disponibles: " + ", ".join(self.asientos))
        if self.zonas:
            partes.append("sin entradas suficientes en las zonas: " + ", ".join(map(str, self.zonas)))
        return "; ".join(partes) or "no disponible"


class ReservaNoVigente(Exception):
    """La reserva vencio o fue cancelada."""


class EventoNoALaVenta(Exception):
    pass


def _exigir_evento_a_la_venta(session: Session, evento_id: int) -> None:
    """FOR SHARE: reservas y pagos no se frenan entre si, pero quedan
    serializados con el UPDATE de una cancelacion."""
    cerrado = session.execute(
        text("SELECT cancelado OR (fecha_inicio IS NOT NULL AND fecha_inicio <= now()) "
             "FROM inventario_eventos WHERE evento_id = :e FOR SHARE"),
        {"e": evento_id},
    ).scalar()
    if cerrado:
        raise EventoNoALaVenta()


class ReservaPagada(Exception):
    pass


class DevolucionYaExiste(Exception):
    """El item ya tiene una devolucion pendiente o aprobada."""


class DevolucionYaResuelta(Exception):
    """La devolucion ya fue aprobada o rechazada."""


class EventoFinalizado(Exception):
    """El evento ya comenzo y no fue cancelado."""


@dataclass(frozen=True)
class PedidoReserva:
    evento_id: int
    asientos: tuple[int, ...]  # ids de tickets numerados
    generales: tuple[tuple[int, int], ...]  # (zona_id, cantidad)

    @property
    def cantidad(self) -> int:
        return len(self.asientos) + sum(c for _, c in self.generales)

    def huella(self) -> str:
        """Hash del contenido, para detectar una clave reutilizada con otro pedido."""
        canonico = {
            "evento_id": self.evento_id,
            "asientos": sorted(self.asientos),
            "generales": sorted(self.generales),
        }
        return hashlib.sha256(json.dumps(canonico, sort_keys=True).encode()).hexdigest()


# --- Inventario -----------------------------------------------------------------

def recibir_inventario(session: Session, inventario: dict) -> bool:
    """Crea un ticket por entrada. Idempotente por evento: devuelve False si
    el inventario ya se habia recibido (y no crea nada)."""
    evento_id = inventario["evento_id"]
    creado = session.execute(
        pg_insert(InventarioEvento).values(evento_id=evento_id, fecha_inicio=inventario.get("fecha_inicio"))
        .on_conflict_do_nothing(index_elements=["evento_id"])
        .returning(InventarioEvento.evento_id)
    ).first()
    if creado is None:
        session.rollback()
        return False

    filas = []
    for zona in inventario["zonas"]:
        base = {"evento_id": evento_id, "zona_id": zona["zona_id"], "tipo_zona": zona["tipo"],
                "precio": zona["precio"], "estado": "disponible"}
        if zona["tipo"] == "numerada":
            filas += [{**base, "fila": a["fila"], "numero": a["numero"]} for a in zona["asientos"]]
        else:
            filas += [{**base, "fila": None, "numero": None}] * zona["capacidad"]
    if filas:
        session.execute(insert(Ticket), filas)  # insercion en bloque
    session.commit()
    return True


def actualizar_evento(session: Session, evento_id: int, version: int,
                      fecha_inicio=None, cancelar: bool = False) -> bool:
    """Devuelve False si lo ignoro por version. En el SET de PostgreSQL las
    columnas valen lo que tenian ANTES del UPDATE: el CASE depende de eso."""
    aplicado = session.execute(
        text(
            "UPDATE inventario_eventos SET "
            "  version = :v, "
            "  cancelado = cancelado OR :cancelar, "
            "  fecha_inicio = CASE WHEN cancelado THEN fecha_inicio "
            "                      ELSE COALESCE(CAST(:fecha AS timestamptz), fecha_inicio) END "
            "WHERE evento_id = :e AND version < :v "
            "RETURNING evento_id"
        ),
        {"v": version, "cancelar": cancelar, "fecha": fecha_inicio, "e": evento_id},
    ).first()
    if aplicado is None and session.get(InventarioEvento, evento_id) is None:
        session.rollback()
        raise NoEncontrado()
    session.commit()
    return aplicado is not None


# --- Disponibilidad -------------------------------------------------------------

def disponibilidad(session: Session, evento_id: int) -> dict:
    a_la_venta = session.execute(
        text(
            "SELECT (NOT cancelado) AND (fecha_inicio IS NULL OR fecha_inicio > now()) "
            "FROM inventario_eventos WHERE evento_id = :e"
        ),
        {"e": evento_id},
    ).scalar()
    if a_la_venta is None:
        raise NoEncontrado()
    filas = session.execute(
        text(
            f"SELECT t.id, t.zona_id, t.tipo_zona, t.fila, t.numero, t.precio, {DISPONIBLE_EFECTIVO} AS libre "
            "FROM tickets t WHERE t.evento_id = :e ORDER BY t.zona_id, t.fila, t.numero, t.id"
        ),
        {"e": evento_id},
    ).all()

    zonas: dict[int, dict] = {}
    for f in filas:
        zona = zonas.setdefault(f.zona_id, {
            "zona_id": f.zona_id, "tipo": f.tipo_zona, "precio": float(f.precio),
            "disponibles": 0, "total": 0, "asientos": [],
        })
        zona["total"] += 1
        zona["disponibles"] += int(f.libre)
        if f.tipo_zona == "numerada":
            zona["asientos"].append({"ticket_id": f.id, "fila": f.fila, "numero": f.numero, "disponible": f.libre})
    return {"evento_id": evento_id, "a_la_venta": bool(a_la_venta), "zonas": list(zonas.values())}


# --- Reserva ----------------------------------------------------------------------

def reservar(session: Session, user_id: int, clave: str, pedido: PedidoReserva,
             ttl_minutos: int, max_tickets: int) -> Reserva:
    if pedido.cantidad == 0:
        raise Invalido("la reserva no tiene tickets")
    if pedido.cantidad > max_tickets:
        raise Invalido(f"una reserva admite como maximo {max_tickets} tickets")
    if len(set(pedido.asientos)) != len(pedido.asientos):
        raise Invalido("asientos repetidos")

    try:
        session.execute(text("SET LOCAL lock_timeout = '2s'"))

        # 1. Idempotencia: la clave se inserta primero. Si otra transaccion con
        #    la misma clave esta en curso, este INSERT espera a que termine.
        propia = session.execute(
            pg_insert(IdempotencyKey)
            .values(user_id=user_id, key=clave, request_hash=pedido.huella())
            .on_conflict_do_nothing(constraint="uq_idempotency_user_key")
            .returning(IdempotencyKey.id)
        ).scalar()
        if propia is None:
            return _reserva_previa(session, user_id, clave, pedido)

        # 1b. Evento cancelado o ya iniciado. El rollback descarta la clave.
        try:
            _exigir_evento_a_la_venta(session, pedido.evento_id)
        except EventoNoALaVenta:
            session.rollback()
            raise

        # 2. La reserva, con su vencimiento calculado por la base.
        reserva_id, hasta = session.execute(
            text(
                "INSERT INTO reservas (user_id, evento_id, cantidad, hasta, estado) "
                "VALUES (:u, :e, :c, now() + make_interval(mins => :ttl), 'activa') RETURNING id, hasta"
            ),
            {"u": user_id, "e": pedido.evento_id, "c": pedido.cantidad, "ttl": ttl_minutos},
        ).one()

        # 3. Numerados: UPDATE condicional por asiento, en orden de id (evita
        #    deadlocks entre reservas cruzadas).
        no_disponibles = []
        for ticket_id in sorted(pedido.asientos):
            tomado = session.execute(
                text(
                    "UPDATE tickets t SET estado = 'reservado', reserva_id = :r, reservado_hasta = :h "
                    f"WHERE t.id = :id AND t.evento_id = :e AND t.tipo_zona = 'numerada' AND {DISPONIBLE_EFECTIVO} "
                    "RETURNING t.id"
                ),
                {"r": reserva_id, "h": hasta, "id": ticket_id, "e": pedido.evento_id},
            ).first()
            if tomado is None:
                no_disponibles.append(ticket_id)

        # 4. Generales: SKIP LOCKED para que reservas simultaneas tomen
        #    tickets distintos en lugar de esperarse.
        zonas_sin_cupo = []
        for zona_id, cantidad in pedido.generales:
            ids = session.execute(
                text(
                    "SELECT t.id FROM tickets t "
                    f"WHERE t.zona_id = :z AND t.evento_id = :e AND t.tipo_zona = 'general' AND {DISPONIBLE_EFECTIVO} "
                    "ORDER BY t.id LIMIT :n FOR UPDATE SKIP LOCKED"
                ),
                {"z": zona_id, "e": pedido.evento_id, "n": cantidad},
            ).scalars().all()
            if len(ids) < cantidad:
                zonas_sin_cupo.append(zona_id)
                continue
            session.execute(
                text("UPDATE tickets SET estado = 'reservado', reserva_id = :r, reservado_hasta = :h "
                     "WHERE id = ANY(:ids)"),
                {"r": reserva_id, "h": hasta, "ids": list(ids)},
            )

        if no_disponibles or zonas_sin_cupo:
            asientos = _nombres_de_asientos(session, no_disponibles)
            session.rollback()  # tambien descarta la clave: el reintento se evalua de nuevo
            raise NoDisponible(asientos=asientos, zonas=zonas_sin_cupo)

        session.execute(
            text("UPDATE idempotency_keys SET reserva_id = :r WHERE id = :k"), {"r": reserva_id, "k": propia}
        )
        session.commit()
    except DBAPIError as error:
        session.rollback()
        # 55P03 = lock_not_available: otra reserva retuvo la fila mas de lock_timeout.
        if getattr(error.orig, "sqlstate", None) == "55P03":
            raise NoDisponible() from error
        raise
    return session.get(Reserva, reserva_id)


def _reserva_previa(session: Session, user_id: int, clave: str, pedido: PedidoReserva) -> Reserva:
    previa = session.scalar(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == clave)
    )
    session.rollback()
    if previa.request_hash != pedido.huella():
        raise ClaveReutilizada()
    return session.get(Reserva, previa.reserva_id)


def _nombres_de_asientos(session: Session, ticket_ids: list[int]) -> list[str]:
    if not ticket_ids:
        return []
    filas = session.execute(
        text("SELECT id, fila, numero FROM tickets WHERE id = ANY(:ids) ORDER BY id"), {"ids": ticket_ids}
    ).all()
    encontrados = {f.id: f"{f.fila}-{f.numero}" for f in filas}
    return [encontrados.get(i, f"ticket {i}") for i in ticket_ids]


def obtener_reserva(session: Session, reserva_id: int, user_id: int) -> Reserva:
    reserva = session.get(Reserva, reserva_id)
    if reserva is None or reserva.user_id != user_id:
        raise NoEncontrado()  # una reserva ajena "no existe"
    return reserva


def tickets_de_reserva(session: Session, reserva_id: int) -> list[Ticket]:
    return list(session.scalars(
        select(Ticket).where((Ticket.reserva_id == reserva_id) | (Ticket.orden_id.in_(
            select(Orden.id).where(Orden.reserva_id == reserva_id)
        ))).order_by(Ticket.id)
    ))


def reserva_vigente(session: Session, reserva: Reserva) -> bool:
    return reserva.estado == ACTIVA and session.scalar(
        text("SELECT :h > now()"), {"h": reserva.hasta}
    )


# --- Pago ---------------------------------------------------------------------

def pagar(session: Session, reserva_id: int, user_id: int) -> Orden:
    """Pago simulado (siempre aprueba). Idempotente por estado: pagar una
    reserva ya pagada devuelve la misma orden."""
    reserva = obtener_reserva(session, reserva_id, user_id)
    if reserva.estado == PAGADA:
        return _orden_de(session, reserva_id)

    try:
        _exigir_evento_a_la_venta(session, reserva.evento_id)
    except EventoNoALaVenta:
        session.rollback()
        raise

    marcada = session.execute(
        text("UPDATE reservas SET estado = 'pagada' "
             "WHERE id = :r AND user_id = :u AND estado = 'activa' AND hasta > now() RETURNING id"),
        {"r": reserva_id, "u": user_id},
    ).first()
    if marcada is None:
        session.rollback()
        # Otro pago concurrente pudo haberla pagado mientras esperabamos el lock.
        session.expire_all()
        if session.get(Reserva, reserva_id).estado == PAGADA:
            return _orden_de(session, reserva_id)
        raise ReservaNoVigente()

    orden_id = session.execute(
        insert(Orden).values(user_id=user_id, reserva_id=reserva_id, total=0).returning(Orden.id)
    ).scalar_one()
    vendidos = session.execute(
        text("UPDATE tickets SET estado = 'vendido', orden_id = :o, reservado_hasta = NULL "
             "WHERE reserva_id = :r AND estado = 'reservado' AND reservado_hasta > now() "
             "RETURNING id, precio"),
        {"o": orden_id, "r": reserva_id},
    ).all()
    if len(vendidos) != reserva.cantidad:
        # Algun ticket fue tomado por otra reserva justo al vencer.
        session.rollback()
        raise ReservaNoVigente()

    session.execute(insert(OrdenItem), [{"orden_id": orden_id, "ticket_id": v.id, "precio": v.precio} for v in vendidos])
    session.execute(
        text("UPDATE ordenes SET total = :t WHERE id = :o"), {"t": sum(v.precio for v in vendidos), "o": orden_id}
    )
    session.commit()
    return session.get(Orden, orden_id)


def _orden_de(session: Session, reserva_id: int) -> Orden:
    return session.scalar(select(Orden).where(Orden.reserva_id == reserva_id))


# --- Cancelacion ----------------------------------------------------------------

def cancelar(session: Session, reserva_id: int, user_id: int) -> None:
    reserva = obtener_reserva(session, reserva_id, user_id)
    if reserva.estado == PAGADA:
        raise ReservaPagada()
    if reserva.estado == CANCELADA:
        return
    cambiada = session.execute(
        text("UPDATE reservas SET estado = 'cancelada' WHERE id = :r AND estado = 'activa' RETURNING id"),
        {"r": reserva_id},
    ).first()
    if cambiada is None:  # la pagaron entre la lectura y el UPDATE
        session.rollback()
        raise ReservaPagada()
    session.execute(
        text("UPDATE tickets SET estado = 'disponible', reserva_id = NULL, reservado_hasta = NULL "
             "WHERE reserva_id = :r AND estado = 'reservado'"),
        {"r": reserva_id},
    )
    session.commit()


# --- Historial ----------------------------------------------------------------------

def compras_de(session: Session, user_id: int) -> list[dict]:
    ordenes = session.scalars(select(Orden).where(Orden.user_id == user_id).order_by(Orden.id)).all()
    if not ordenes:
        return []

    orden_ids = [o.id for o in ordenes]
    filas_items = session.execute(
        text(
            "SELECT oi.id AS orden_item_id, oi.orden_id, t.id AS ticket_id, t.evento_id, "
            "  t.zona_id, t.tipo_zona, t.fila, t.numero, oi.precio, "
            "  ie.fecha_inicio AS evento_fecha_inicio, "
            "  COALESCE(ie.cancelado, FALSE) AS evento_cancelado, "
            "  CASE "
            "    WHEN COALESCE(ie.cancelado, FALSE) THEN 'cancelado' "
            "    WHEN ie.fecha_inicio IS NOT NULL AND ie.fecha_inicio <= now() THEN 'finalizado' "
            "    ELSE 'activo' "
            "  END AS evento_estado "
            "FROM orden_items oi "
            "JOIN tickets t ON t.id = oi.ticket_id "
            "LEFT JOIN inventario_eventos ie ON ie.evento_id = t.evento_id "
            "WHERE oi.orden_id = ANY(:orden_ids) "
            "ORDER BY oi.orden_id, t.id"
        ),
        {"orden_ids": orden_ids},
    ).all()

    item_ids = [i.orden_item_id for i in filas_items]
    ultimas_devoluciones: dict[int, dict] = {}
    if item_ids:
        filas_dev = session.execute(
            text(
                "SELECT DISTINCT ON (orden_item_id) "
                "  id, orden_item_id, estado, motivo, nota_resolucion, created_at, resuelto_at "
                "FROM devoluciones "
                "WHERE orden_item_id = ANY(:item_ids) "
                "ORDER BY orden_item_id, id DESC"
            ),
            {"item_ids": item_ids},
        ).all()
        ultimas_devoluciones = {
            d.orden_item_id: {
                "id": d.id,
                "estado": d.estado,
                "motivo": d.motivo,
                "nota_resolucion": d.nota_resolucion,
                "created_at": d.created_at,
                "resuelto_at": d.resuelto_at,
            }
            for d in filas_dev
        }

    items_por_orden: dict[int, list[dict]] = {o.id: [] for o in ordenes}
    for i in filas_items:
        items_por_orden[i.orden_id].append({
            "orden_item_id": i.orden_item_id,
            "ticket_id": i.ticket_id,
            "evento_id": i.evento_id,
            "zona_id": i.zona_id,
            "tipo_zona": i.tipo_zona,
            "fila": i.fila,
            "numero": i.numero,
            "precio": float(i.precio),
            "evento_fecha_inicio": i.evento_fecha_inicio,
            "evento_cancelado": bool(i.evento_cancelado),
            "evento_estado": i.evento_estado,
            "devolucion": ultimas_devoluciones.get(i.orden_item_id),
        })

    return [
        {
            "id": orden.id,
            "reserva_id": orden.reserva_id,
            "total": float(orden.total),
            "created_at": orden.created_at,
            "tickets": items_por_orden[orden.id],
        }
        for orden in ordenes
    ]


# --- Devoluciones -------------------------------------------------------------------

def _formatear_devolucion(fila) -> dict:
    return {
        "id": fila.id,
        "orden_item_id": fila.orden_item_id,
        "orden_id": fila.orden_id,
        "ticket_id": fila.ticket_id,
        "user_id": fila.user_id,
        "evento_id": fila.evento_id,
        "zona_id": fila.zona_id,
        "tipo_zona": fila.tipo_zona,
        "fila": fila.fila,
        "numero": fila.numero,
        "precio": float(fila.precio),
        "estado": fila.estado,
        "motivo": fila.motivo,
        "nota_resolucion": fila.nota_resolucion,
        "resuelto_por": fila.resuelto_por,
        "resuelto_at": fila.resuelto_at,
        "created_at": fila.created_at,
        "evento_fecha_inicio": fila.evento_fecha_inicio,
        "evento_cancelado": bool(fila.evento_cancelado),
    }


def _detalle_devolucion(session: Session, devolucion_id: int) -> dict:
    fila = session.execute(
        text(
            "SELECT d.id, d.orden_item_id, d.orden_id, d.ticket_id, d.user_id, "
            "  t.evento_id, t.zona_id, t.tipo_zona, t.fila, t.numero, oi.precio, "
            "  d.estado, d.motivo, d.nota_resolucion, d.resuelto_por, d.resuelto_at, d.created_at, "
            "  ie.fecha_inicio AS evento_fecha_inicio, COALESCE(ie.cancelado, FALSE) AS evento_cancelado "
            "FROM devoluciones d "
            "JOIN orden_items oi ON oi.id = d.orden_item_id "
            "JOIN tickets t ON t.id = d.ticket_id "
            "LEFT JOIN inventario_eventos ie ON ie.evento_id = t.evento_id "
            "WHERE d.id = :id"
        ),
        {"id": devolucion_id},
    ).first()
    if fila is None:
        raise NoEncontrado()
    return _formatear_devolucion(fila)


def solicitar_devolucion(session: Session, user_id: int, orden_item_id: int,
                         motivo: str | None = None) -> dict:
    item = session.execute(
        text(
            "SELECT oi.id AS orden_item_id, oi.orden_id, oi.ticket_id, t.evento_id, "
            "  t.estado AS ticket_estado, t.orden_id AS ticket_orden_id "
            "FROM orden_items oi "
            "JOIN ordenes o ON o.id = oi.orden_id "
            "JOIN tickets t ON t.id = oi.ticket_id "
            "WHERE oi.id = :item_id AND o.user_id = :user_id"
        ),
        {"item_id": orden_item_id, "user_id": user_id},
    ).first()
    if item is None:
        raise NoEncontrado()

    # FOR SHARE sobre inventario_eventos para serializar con cancelaciones/reprogramaciones.
    # Un evento cancelado SIEMPRE permite solicitar devolucion; uno finalizado (no cancelado), no.
    finalizado = session.execute(
        text(
            "SELECT (NOT cancelado) AND (fecha_inicio IS NOT NULL AND fecha_inicio <= now()) "
            "FROM inventario_eventos WHERE evento_id = :e FOR SHARE"
        ),
        {"e": item.evento_id},
    ).scalar()
    if finalizado:
        session.rollback()
        raise EventoFinalizado()

    if item.ticket_estado != "vendido" or item.ticket_orden_id != item.orden_id:
        session.rollback()
        raise DevolucionYaExiste()

    motivo_limpio = motivo.strip() if motivo is not None else None
    if motivo_limpio == "":
        motivo_limpio = None

    try:
        creada_id = session.execute(
            pg_insert(Devolucion)
            .values(
                orden_item_id=item.orden_item_id,
                orden_id=item.orden_id,
                ticket_id=item.ticket_id,
                user_id=user_id,
                estado=DEVOLUCION_PENDIENTE,
                motivo=motivo_limpio,
            )
            .on_conflict_do_nothing(
                index_elements=["orden_item_id"],
                index_where=text("estado IN ('pendiente', 'aprobada')"),
            )
            .returning(Devolucion.id)
        ).scalar()
    except IntegrityError as error:
        session.rollback()
        raise DevolucionYaExiste() from error

    if creada_id is None:
        session.rollback()
        raise DevolucionYaExiste()

    session.commit()
    return _detalle_devolucion(session, creada_id)


def listar_devoluciones(session: Session, user_id: int, rol: str, estado: str | None = None) -> list[dict]:
    if estado is not None and estado not in ESTADOS_DEVOLUCION:
        raise Invalido("estado de devolucion invalido")

    condiciones = []
    params: dict = {}
    if rol == "cliente":
        condiciones.append("d.user_id = :user_id")
        params["user_id"] = user_id
    if estado is not None:
        condiciones.append("d.estado = :estado")
        params["estado"] = estado

    where = f"WHERE {' AND '.join(condiciones)} " if condiciones else ""
    filas = session.execute(
        text(
            "SELECT d.id, d.orden_item_id, d.orden_id, d.ticket_id, d.user_id, "
            "  t.evento_id, t.zona_id, t.tipo_zona, t.fila, t.numero, oi.precio, "
            "  d.estado, d.motivo, d.nota_resolucion, d.resuelto_por, d.resuelto_at, d.created_at, "
            "  ie.fecha_inicio AS evento_fecha_inicio, COALESCE(ie.cancelado, FALSE) AS evento_cancelado "
            "FROM devoluciones d "
            "JOIN orden_items oi ON oi.id = d.orden_item_id "
            "JOIN tickets t ON t.id = d.ticket_id "
            "LEFT JOIN inventario_eventos ie ON ie.evento_id = t.evento_id "
            f"{where}"
            "ORDER BY d.created_at DESC, d.id DESC"
        ),
        params,
    ).all()
    return [_formatear_devolucion(f) for f in filas]


def aprobar_devolucion(session: Session, devolucion_id: int, admin_id: int,
                       nota: str | None = None) -> dict:
    nota_limpia = nota.strip() if nota is not None else None
    if nota_limpia == "":
        nota_limpia = None

    marcada = session.execute(
        text(
            "UPDATE devoluciones "
            "SET estado = 'aprobada', resuelto_por = :admin, nota_resolucion = :nota, resuelto_at = now() "
            "WHERE id = :id AND estado = 'pendiente' "
            "RETURNING id, ticket_id, orden_id"
        ),
        {"id": devolucion_id, "admin": admin_id, "nota": nota_limpia},
    ).first()
    if marcada is None:
        session.rollback()
        if session.get(Devolucion, devolucion_id) is None:
            raise NoEncontrado()
        raise DevolucionYaResuelta()

    # Libera el ticket: en zona numerada vuelve disponible el asiento exacto;
    # en zona general vuelve al pool disponible (+1 al cupo de la zona).
    liberado = session.execute(
        text(
            "UPDATE tickets "
            "SET estado = 'disponible', reserva_id = NULL, reservado_hasta = NULL, orden_id = NULL "
            "WHERE id = :ticket_id AND orden_id = :orden_id AND estado = 'vendido' "
            "RETURNING id"
        ),
        {"ticket_id": marcada.ticket_id, "orden_id": marcada.orden_id},
    ).first()
    if liberado is None:
        session.rollback()
        raise DevolucionYaResuelta()

    session.commit()
    return _detalle_devolucion(session, devolucion_id)


def rechazar_devolucion(session: Session, devolucion_id: int, admin_id: int,
                        nota: str | None = None) -> dict:
    nota_limpia = nota.strip() if nota is not None else None
    if nota_limpia == "":
        nota_limpia = None

    marcada = session.execute(
        text(
            "UPDATE devoluciones "
            "SET estado = 'rechazada', resuelto_por = :admin, nota_resolucion = :nota, resuelto_at = now() "
            "WHERE id = :id AND estado = 'pendiente' "
            "RETURNING id"
        ),
        {"id": devolucion_id, "admin": admin_id, "nota": nota_limpia},
    ).first()
    if marcada is None:
        session.rollback()
        if session.get(Devolucion, devolucion_id) is None:
            raise NoEncontrado()
        raise DevolucionYaResuelta()

    session.commit()
    return _detalle_devolucion(session, devolucion_id)
