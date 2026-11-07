"""Tests de la propia infraestructura de tests (guarda y rollback por test)."""

import pytest
from sqlalchemy import text

from tests.conftest import verificar_base_de_test


def test_guarda_rechaza_base_que_no_es_de_test():
    with pytest.raises(RuntimeError):
        verificar_base_de_test("postgresql+psycopg://ventas:x@postgres:5432/ventas_db")


def test_guarda_acepta_base_de_test():
    verificar_base_de_test("postgresql+psycopg://ventas:x@localhost:5433/ventas_db_test")


def test_rollback_1_crea_tabla_e_inserta(db_session):
    db_session.execute(text("CREATE TABLE verif_rollback (x int)"))
    db_session.execute(text("INSERT INTO verif_rollback VALUES (1)"))
    assert db_session.execute(text("SELECT count(*) FROM verif_rollback")).scalar() == 1


def test_rollback_2_la_tabla_no_existe(db_session):
    # El test anterior se revirtio entero (PostgreSQL revierte tambien el DDL).
    existe = db_session.execute(
        text("SELECT to_regclass('public.verif_rollback') IS NOT NULL")
    ).scalar()
    assert existe is False


def test_health_con_base_responde_200(client):
    assert client.get("/health").status_code == 200
