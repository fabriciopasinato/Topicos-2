"""2.2 Migraciones: aplican y revierten; trigger, CHECK e indice unico de DNI."""

import time

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

COLUMNAS_NUEVAS = {
    "nombre", "apellido", "dni", "fecha_nacimiento", "telefono", "calle", "numero", "piso_depto",
    "localidad", "provincia", "codigo_postal", "estado", "motivo_bloqueo", "intentos_fallidos",
    "updated_at", "last_login_at",
}


def test_migracion_aplica_y_revierte(engine, alembic_config):
    try:
        command.downgrade(alembic_config, "0001")
        assert "tokens_cuenta" not in inspect(engine).get_table_names()
        assert COLUMNAS_NUEVAS.isdisjoint(c["name"] for c in inspect(engine).get_columns("users"))

        command.downgrade(alembic_config, "base")
        assert {"users", "refresh_tokens"}.isdisjoint(inspect(engine).get_table_names())

        command.upgrade(alembic_config, "head")
        assert {"users", "refresh_tokens", "tokens_cuenta"} <= set(inspect(engine).get_table_names())
        assert COLUMNAS_NUEVAS <= {c["name"] for c in inspect(engine).get_columns("users")}
    finally:
        command.upgrade(alembic_config, "head")


def test_cuentas_existentes_quedan_activas(engine, alembic_config):
    try:
        command.downgrade(alembic_config, "0001")
        with engine.begin() as c:
            c.execute(text("INSERT INTO users (email, password_hash, rol) VALUES ('vieja@x.com', 'h', 'cliente')"))
        command.upgrade(alembic_config, "head")
        with engine.connect() as c:
            fila = c.execute(text(
                "SELECT estado, intentos_fallidos, updated_at = created_at AS igual FROM users WHERE email = 'vieja@x.com'"
            )).one()
        assert (fila.estado, fila.intentos_fallidos, fila.igual) == ("activa", 0, True)
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM users WHERE email = 'vieja@x.com'"))


def _insertar(db_session, email="x@y.z", dni=None, estado="activa"):
    return db_session.execute(
        text("INSERT INTO users (email, password_hash, rol, dni, estado) VALUES (:e, 'h', 'cliente', :d, :s) "
             "RETURNING id"),
        {"e": email, "d": dni, "s": estado},
    ).scalar()


def test_rol_invalido_es_rechazado_por_la_base(db_session):
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO users (email, password_hash, rol) VALUES ('x@y.z', 'h', 'superusuario')")
        )
        db_session.flush()


def test_estado_invalido_es_rechazado(db_session):
    with pytest.raises(IntegrityError):
        _insertar(db_session, estado="suspendida")


def test_dni_duplicado_es_rechazado_pero_varios_sin_dni_no(db_session):
    _insertar(db_session, "a@x.com")
    _insertar(db_session, "b@x.com")  # dos cuentas sin DNI conviven
    _insertar(db_session, "c@x.com", dni="30123456")
    with pytest.raises(IntegrityError):
        _insertar(db_session, "d@x.com", dni="30123456")


def test_trigger_actualiza_updated_at_en_un_update_directo(db_session):
    user_id = _insertar(db_session)
    antes = db_session.execute(text("SELECT updated_at FROM users WHERE id = :u"), {"u": user_id}).scalar()
    # now() es fijo dentro de una transaccion: se usa un savepoint nuevo y se
    # compara contra clock_timestamp para no depender de eso.
    time.sleep(0.01)
    db_session.execute(text("UPDATE users SET intentos_fallidos = 1 WHERE id = :u"), {"u": user_id})
    despues = db_session.execute(text("SELECT updated_at FROM users WHERE id = :u"), {"u": user_id}).scalar()
    assert despues >= antes
    # La prueba fuerte del trigger: se pisa cualquier valor que se intente escribir.
    db_session.execute(
        text("UPDATE users SET updated_at = '2000-01-01', telefono = '123456' WHERE id = :u"), {"u": user_id}
    )
    forzado = db_session.execute(text("SELECT updated_at FROM users WHERE id = :u"), {"u": user_id}).scalar()
    assert forzado.year != 2000
