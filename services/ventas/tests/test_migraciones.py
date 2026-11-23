import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

TABLAS = {"inventario_eventos", "tickets", "reservas", "ordenes", "orden_items", "idempotency_keys"}


def test_migracion_aplica_y_revierte(engine, alembic_config):
    try:
        command.downgrade(alembic_config, "base")
        assert TABLAS.isdisjoint(inspect(engine).get_table_names())
        command.upgrade(alembic_config, "head")
        assert TABLAS <= set(inspect(engine).get_table_names())
    finally:
        command.upgrade(alembic_config, "head")


def test_migracion_0002_conserva_inventarios_existentes(engine, alembic_config):
    """Un inventario recibido antes de 0002 queda sin fecha, no cancelado y en
    version 0, asi sigue vendiendose como antes."""
    try:
        command.downgrade(alembic_config, "0001")
        with engine.begin() as conexion:
            conexion.execute(text("INSERT INTO inventario_eventos (evento_id) VALUES (999)"))
        command.upgrade(alembic_config, "head")
        with engine.connect() as conexion:
            fila = conexion.execute(
                text("SELECT fecha_inicio, cancelado, version FROM inventario_eventos WHERE evento_id = 999")
            ).one()
        assert fila == (None, False, 0)

        command.downgrade(alembic_config, "0001")
        columnas = {c["name"] for c in inspect(engine).get_columns("inventario_eventos")}
        assert columnas.isdisjoint({"fecha_inicio", "cancelado", "version"})
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as conexion:
            conexion.execute(text("DELETE FROM inventario_eventos WHERE evento_id = 999"))


def test_indice_unico_rechaza_asiento_numerado_duplicado(db_session):
    fila = ("INSERT INTO tickets (evento_id, zona_id, tipo_zona, fila, numero, precio) "
            "VALUES (1, 1, 'numerada', 'A', 1, 100)")
    db_session.execute(text(fila))
    with pytest.raises(IntegrityError):
        db_session.execute(text(fila))


def test_tickets_generales_no_chocan_con_el_indice_unico(db_session):
    general = ("INSERT INTO tickets (evento_id, zona_id, tipo_zona, precio) "
               "VALUES (1, 2, 'general', 50)")
    db_session.execute(text(general))
    db_session.execute(text(general))
    assert db_session.scalar(text("SELECT count(*) FROM tickets")) == 2
