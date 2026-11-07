"""Tests de la propia infraestructura de tests (guarda y limpieza por test)."""

import pytest
from sqlalchemy import text

from tests.conftest import verificar_base_de_test


def test_guarda_rechaza_base_que_no_es_de_test():
    with pytest.raises(RuntimeError):
        verificar_base_de_test("postgresql+asyncpg://gateway:x@postgres:5432/gateway_db")


def test_guarda_acepta_base_de_test():
    verificar_base_de_test("postgresql+asyncpg://gateway:x@localhost:5433/gateway_db_test")


def test_limpieza_1_inserta_fila(engine_sync, redis_sync):
    with engine_sync.begin() as conexion:
        conexion.execute(text("CREATE TABLE IF NOT EXISTS verif_limpieza (x int)"))
        conexion.execute(text("INSERT INTO verif_limpieza VALUES (1)"))
    redis_sync.set("verif", "1")


def test_limpieza_2_la_tabla_y_redis_estan_vacios(engine_sync, redis_sync):
    with engine_sync.begin() as conexion:
        filas = conexion.execute(text("SELECT count(*) FROM verif_limpieza")).scalar()
        conexion.execute(text("DROP TABLE verif_limpieza"))
    assert filas == 0
    assert redis_sync.get("verif") is None


def test_health_con_base_y_redis_responde_200(client):
    assert client.get("/health").status_code == 200
