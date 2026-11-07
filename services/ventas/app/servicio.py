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
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import (
    ACTIVA, CANCELADA, PAGADA, IdempotencyKey, InventarioEvento, Orden, OrdenItem, Reserva, Ticket,
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


class ReservaPagada(Exception):
    pass


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
        pg_insert(InventarioEvento).values(evento_id=evento_id)
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


# --- Disponibilidad -------------------------------------------------------------

def disponibilidad(session: Session, evento_id: int) -> list[dict]:
    if session.get(InventarioEvento, evento_id) is None:
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
    return list(zonas.values())


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
    resultado = []
    for orden in ordenes:
        items = session.execute(
            select(Ticket.id, Ticket.evento_id, Ticket.zona_id, Ticket.fila, Ticket.numero, OrdenItem.precio)
            .join(OrdenItem, OrdenItem.ticket_id == Ticket.id)
            .where(OrdenItem.orden_id == orden.id)
            .order_by(Ticket.id)
        ).all()
        resultado.append({
            "id": orden.id, "reserva_id": orden.reserva_id, "total": float(orden.total),
            "created_at": orden.created_at,
            "tickets": [{"ticket_id": i.id, "evento_id": i.evento_id, "zona_id": i.zona_id,
                         "fila": i.fila, "numero": i.numero, "precio": float(i.precio)} for i in items],
        })
    return resultado
