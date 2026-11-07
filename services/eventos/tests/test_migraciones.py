from alembic import command
from sqlalchemy import inspect

TABLAS = {"recintos", "eventos", "sectores", "zonas", "asientos"}


def test_migracion_aplica_y_revierte(engine, alembic_config):
    try:
        command.downgrade(alembic_config, "base")
        assert TABLAS.isdisjoint(inspect(engine).get_table_names())
        command.upgrade(alembic_config, "head")
        assert TABLAS <= set(inspect(engine).get_table_names())
    finally:
        command.upgrade(alembic_config, "head")
