"""Fixtures comunes de tests.

- Los tests corren SOLO contra una base cuyo nombre termina en "_test"
  (TEST_DATABASE_URL). Nunca contra la base de desarrollo.
- `db_session` / `client`: cada test corre dentro de una transaccion que se
  revierte al terminar, asi cada test arranca con la base limpia.
- `db_concurrente`: para tests de concurrencia, que necesitan conexiones reales
  en paralelo y commits visibles entre ellas. Limpia con TRUNCATE al final.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

SERVICIO_DIR = Path(__file__).resolve().parent.parent

# Base de test por defecto: la de docker-compose.test.yml (puerto 5433).
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://auth:auth_test@localhost:5433/auth_db_test",
)


def verificar_base_de_test(url: str) -> None:
    """Aborta si la URL no apunta a una base de test."""
    nombre = make_url(url).database or ""
    if not nombre.endswith("_test"):
        raise RuntimeError(
            f"Los tests solo corren contra una base '*_test' y se recibio '{nombre}'."
        )


try:
    verificar_base_de_test(TEST_DATABASE_URL)
except RuntimeError as error:
    pytest.exit(str(error), returncode=2)

# La app lee DATABASE_URL: se fija ANTES de importarla.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "secreto-de-test")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import Base, get_engine, get_session  # noqa: E402
from app.main import app  # noqa: E402


def _alembic_config() -> Config:
    cfg = Config(str(SERVICIO_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICIO_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    return _alembic_config()


@pytest.fixture(scope="session")
def engine(alembic_config):
    command.upgrade(alembic_config, "head")
    eng = get_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine):
    """Sesion dentro de una transaccion que se revierte al terminar el test."""
    conexion = engine.connect()
    transaccion = conexion.begin()
    session = Session(bind=conexion, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def client(db_session):
    """TestClient cuya sesion de base es la del test (con rollback)."""

    def sesion_de_test():
        yield db_session

    app.dependency_overrides[get_session] = sesion_de_test
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def db_concurrente(engine):
    """Engine con commits reales para tests de concurrencia. Limpia al final."""
    yield engine
    tablas = [t.name for t in Base.metadata.sorted_tables]
    if tablas:
        with engine.begin() as conexion:
            conexion.execute(
                text(f"TRUNCATE {', '.join(tablas)} RESTART IDENTITY CASCADE")
            )
