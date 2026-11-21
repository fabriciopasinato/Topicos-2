"""aplicar(op): aplica en eventos una operacion confirmada por ventas."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import servicio
from app.models import EstadoOperacion, OperacionVentas, TipoOperacion
from tests.helpers import datos_evento

OWNER = {"X-User-Id": "10", "X-User-Role": "event_owner"}
FECHA_ORIGINAL = datetime.now(UTC) + timedelta(days=30)


@pytest.fixture
def evento_id(client, db_session):
    """Evento publicado, como si ventas ya tuviera su inventario."""
    recinto = client.post("/eventos/recintos", json={"nombre": "Estadio"}, headers=OWNER).json()["id"]
    evento_id = client.post("/eventos", json=datos_evento(recinto), headers=OWNER).json()["id"]
    db_session.execute(text("UPDATE eventos SET estado = 'publicado', fecha = :f WHERE id = :e"),
                       {"f": FECHA_ORIGINAL, "e": evento_id})
    return evento_id


def _operacion(db_session, evento_id, version, tipo=TipoOperacion.REPROGRAMAR, dias=60) -> int:
    fecha = datetime.now(UTC) + timedelta(days=dias) if tipo == TipoOperacion.REPROGRAMAR else None
    op = OperacionVentas(evento_id=evento_id, tipo=tipo, version=version, fecha=fecha)
    db_session.add(op)
    db_session.execute(text("UPDATE eventos SET version = GREATEST(version, :v) WHERE id = :e"),
                       {"v": version, "e": evento_id})
    db_session.commit()
    return op.id


def _evento(db_session, evento_id):
    db_session.expire_all()
    return db_session.execute(
        text("SELECT estado, fecha, version_aplicada FROM eventos WHERE id = :e"), {"e": evento_id}
    ).one()


def _estado_op(db_session, op_id):
    db_session.expire_all()
    return db_session.get(OperacionVentas, op_id).estado


def test_aplica_una_reprogramacion(db_session, evento_id):
    op = _operacion(db_session, evento_id, 1, dias=60)
    servicio.aplicar(db_session, op)
    estado, fecha, version = _evento(db_session, evento_id)
    assert estado == "publicado" and version == 1
    assert abs((fecha - FECHA_ORIGINAL).days - 30) <= 1
    assert _estado_op(db_session, op) == EstadoOperacion.CONFIRMADA


def test_aplica_una_cancelacion(db_session, evento_id):
    op = _operacion(db_session, evento_id, 1, tipo=TipoOperacion.CANCELAR)
    servicio.aplicar(db_session, op)
    assert _evento(db_session, evento_id)[0] == "cancelado"


def test_operacion_repetida_no_tiene_efecto(db_session, evento_id):
    op = _operacion(db_session, evento_id, 1, dias=60)
    servicio.aplicar(db_session, op)
    antes = _evento(db_session, evento_id)
    servicio.aplicar(db_session, op)
    assert _evento(db_session, evento_id) == antes


def test_operacion_vieja_se_ignora_pero_se_confirma(db_session, evento_id):
    nueva = _operacion(db_session, evento_id, 3, dias=90)
    vieja = _operacion(db_session, evento_id, 2, dias=60)
    servicio.aplicar(db_session, nueva)
    fecha_nueva = _evento(db_session, evento_id)[1]
    servicio.aplicar(db_session, vieja)
    _, fecha, version = _evento(db_session, evento_id)
    assert fecha == fecha_nueva and version == 3
    assert _estado_op(db_session, vieja) == EstadoOperacion.CONFIRMADA  # no queda pendiente para siempre


def test_reprogramacion_posterior_a_una_cancelacion_no_la_revierte(db_session, evento_id):
    cancelar = _operacion(db_session, evento_id, 3, tipo=TipoOperacion.CANCELAR)
    reprogramar = _operacion(db_session, evento_id, 4, dias=60)
    servicio.aplicar(db_session, cancelar)
    servicio.aplicar(db_session, reprogramar)
    estado, fecha, version = _evento(db_session, evento_id)
    assert estado == "cancelado" and fecha == FECHA_ORIGINAL and version == 3


def test_operacion_inexistente_no_falla(db_session):
    servicio.aplicar(db_session, 999_999)


# --- Efectos por tipo de operacion ---------------------------------------------------

def test_todo_tipo_de_operacion_tiene_su_efecto():
    """Un tipo sin efecto no puede caer en un caso por defecto equivocado."""
    assert set(servicio.EFECTOS) == set(TipoOperacion)


def test_lo_que_se_manda_a_ventas_coincide_con_el_cliente_http():
    import inspect

    from app.cliente_ventas import ClienteVentas

    aceptados = set(inspect.signature(ClienteVentas.actualizar_evento).parameters) - {"self", "evento_id", "version"}
    for tipo, efecto in servicio.EFECTOS.items():
        op = OperacionVentas(tipo=tipo, version=1, fecha=datetime.now(UTC))
        assert set(efecto.cambios_para_ventas(op)) <= aceptados, tipo
