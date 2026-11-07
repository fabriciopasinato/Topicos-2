import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_migracion_aplica_y_revierte(engine, alembic_config):
    try:
        command.downgrade(alembic_config, "base")
        assert {"users", "refresh_tokens"}.isdisjoint(inspect(engine).get_table_names())
        command.upgrade(alembic_config, "head")
        assert {"users", "refresh_tokens"} <= set(inspect(engine).get_table_names())
    finally:
        command.upgrade(alembic_config, "head")


def test_rol_invalido_es_rechazado_por_la_base(db_session):
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO users (email, password_hash, rol) VALUES ('x@y.z', 'h', 'superusuario')")
        )
        db_session.flush()
