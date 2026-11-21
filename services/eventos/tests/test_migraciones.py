import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

TABLAS = {
    "recintos", "eventos", "sectores", "zonas", "asientos", "tipos_evento",
    "organizadores", "participantes", "evento_participantes", "operaciones_ventas",
}


def test_migracion_aplica_y_revierte(engine, alembic_config):
    try:
        command.downgrade(alembic_config, "base")
        assert TABLAS.isdisjoint(inspect(engine).get_table_names())
        command.upgrade(alembic_config, "head")
        assert TABLAS <= set(inspect(engine).get_table_names())
    finally:
        command.upgrade(alembic_config, "head")


def test_migracion_0002_completa_los_eventos_existentes(engine, alembic_config):
    """Un evento publicado antes de 0002 queda con tipo 'otro', descripcion
    vacia, sin organizador, versiones en 0 y publicado_at = created_at."""
    try:
        command.downgrade(alembic_config, "0001")
        with engine.begin() as c:
            recinto = c.scalar(text("INSERT INTO recintos (nombre) VALUES ('R') RETURNING id"))
            c.execute(
                text("INSERT INTO eventos (owner_id, nombre, fecha, recinto_id, estado) "
                     "VALUES (1, 'Viejo publicado', now(), :r, 'publicado'), (1, 'Viejo borrador', now(), :r, 'borrador')"),
                {"r": recinto},
            )
        command.upgrade(alembic_config, "head")
        with engine.connect() as c:
            filas = c.execute(text(
                "SELECT nombre, tipo, descripcion, organizador_id, version, version_aplicada, "
                "publicado_at = created_at, publicado_at IS NULL FROM eventos ORDER BY nombre"
            )).all()
        assert filas == [
            ("Viejo borrador", "otro", "", None, 0, 0, None, True),
            ("Viejo publicado", "otro", "", None, 0, 0, True, False),
        ]
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as c:
            c.execute(text("TRUNCATE eventos, recintos RESTART IDENTITY CASCADE"))


def test_migracion_crea_los_tipos_iniciales(db_session):
    tipos = dict(db_session.execute(text("SELECT codigo, nombre FROM tipos_evento")).all())
    assert tipos == {
        "recital": "Recital", "teatro": "Teatro", "deporte": "Deporte",
        "conferencia": "Conferencia", "festival": "Festival", "otro": "Otro",
    }


def _evento(db_session, **columnas) -> None:
    recinto = db_session.scalar(text("INSERT INTO recintos (nombre) VALUES ('R') RETURNING id"))
    valores = {"tipo": "recital", "estado": "borrador", **columnas}
    db_session.execute(
        text("INSERT INTO eventos (owner_id, nombre, fecha, recinto_id, tipo, estado) "
             "VALUES (1, 'E', now(), :r, :tipo, :estado)"),
        {"r": recinto, **valores},
    )


def test_fk_rechaza_un_tipo_inexistente(db_session):
    with pytest.raises(IntegrityError):
        _evento(db_session, tipo="stand-up")


def test_la_base_exige_el_tipo_en_las_altas_nuevas(db_session):
    recinto = db_session.scalar(text("INSERT INTO recintos (nombre) VALUES ('R') RETURNING id"))
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO eventos (owner_id, nombre, fecha, recinto_id) VALUES (1, 'E', now(), :r)"),
            {"r": recinto},
        )


def test_tipo_agregado_al_catalogo_se_puede_usar(db_session):
    db_session.execute(text("INSERT INTO tipos_evento (codigo, nombre) VALUES ('stand-up', 'Stand-up')"))
    _evento(db_session, tipo="stand-up")
    assert db_session.scalar(text("SELECT tipo FROM eventos")) == "stand-up"


def test_check_acepta_el_estado_cancelado(db_session):
    _evento(db_session, estado="cancelado")
    assert db_session.scalar(text("SELECT estado FROM eventos")) == "cancelado"


def test_reprogramacion_sin_fecha_se_rechaza(db_session):
    _evento(db_session)
    evento_id = db_session.scalar(text("SELECT id FROM eventos"))
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO operaciones_ventas (evento_id, tipo, version) VALUES (:e, 'reprogramar', 1)"),
            {"e": evento_id},
        )


def test_version_repetida_de_un_evento_se_rechaza(db_session):
    _evento(db_session)
    evento_id = db_session.scalar(text("SELECT id FROM eventos"))
    alta = text("INSERT INTO operaciones_ventas (evento_id, tipo, version) VALUES (:e, 'cancelar', 1)")
    db_session.execute(alta, {"e": evento_id})
    with pytest.raises(IntegrityError):
        db_session.execute(alta, {"e": evento_id})


def test_la_base_acepta_exactamente_los_tipos_y_estados_de_operacion(db_session):
    """Ata los enums del codigo con los checks de la migracion: si se agrega un
    valor a TipoOperacion o EstadoOperacion sin migrar, este test falla."""
    from app.models import EstadoOperacion, TipoOperacion

    _evento(db_session)
    evento_id = db_session.scalar(text("SELECT id FROM eventos"))
    alta = text("INSERT INTO operaciones_ventas (evento_id, tipo, version, fecha, estado) "
                "VALUES (:e, :t, :v, now(), :s)")
    combinaciones = [(t, s) for t in TipoOperacion for s in EstadoOperacion]
    for version, (tipo, estado) in enumerate(combinaciones, start=1):
        db_session.execute(alta, {"e": evento_id, "t": tipo.value, "v": version, "s": estado.value})

    for tipo, estado in [("suspender", "pendiente"), ("cancelar", "fallida")]:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(alta, {"e": evento_id, "t": tipo, "v": 999, "s": estado})
