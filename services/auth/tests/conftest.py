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
# Redis de docker-compose.test.yml (base 1, para no chocar con los tests del gateway).
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL_AUTH", "redis://localhost:6380/1")
os.environ["REDIS_URL"] = TEST_REDIS_URL

import redis  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import revocacion  # noqa: E402
from app.correo import EnviadorFalso, get_enviador  # noqa: E402
from app.db import Base, get_engine, get_session  # noqa: E402
from app.main import app  # noqa: E402

# Datos de registro validos, reutilizables en todos los tests.
DATOS_REGISTRO = {
    "email": "ana@example.com",
    "password": "tortuga-azul-42",
    "nombre": "Ana",
    "apellido": "Pérez",
    "dni": "30123456",
    "fecha_nacimiento": "1990-05-17",
    "telefono": "+54 221 555-1234",
    "calle": "Calle 7",
    "numero": "1234",
    "piso_depto": "3B",
    "localidad": "La Plata",
    "provincia": "Buenos Aires",
    "codigo_postal": "1900",
}


def datos_registro(**cambios) -> dict:
    return {**DATOS_REGISTRO, **cambios}


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
def enviador() -> EnviadorFalso:
    """Reemplaza al SMTP: los emails quedan en enviador.enviados."""
    return EnviadorFalso()


@pytest.fixture
def redis_test():
    cliente = redis.from_url(TEST_REDIS_URL)
    cliente.flushdb()
    yield cliente
    cliente.flushdb()
    cliente.close()


@pytest.fixture
def client(db_session, enviador, redis_test):
    """TestClient cuya sesion de base es la del test (con rollback), con el
    enviador de emails falso y el Redis de test."""

    def sesion_de_test():
        yield db_session

    app.dependency_overrides[get_session] = sesion_de_test
    app.dependency_overrides[get_enviador] = lambda: enviador
    app.dependency_overrides[revocacion.get_redis] = lambda: redis_test
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def token_del_email(email) -> str:
    """Extrae el token del link que viene en un email."""
    return email.cuerpo.split("token=")[1].split()[0]


def activar(db_session, email: str = DATOS_REGISTRO["email"]) -> None:
    db_session.execute(text("UPDATE users SET estado = 'activa' WHERE email = :e"), {"e": email})


@pytest.fixture
def cliente_activo(client, db_session):
    """Un cliente registrado y con el email ya verificado."""
    assert client.post("/auth/registro", json=DATOS_REGISTRO).status_code == 201
    activar(db_session)
    return DATOS_REGISTRO


def login(client, email: str = DATOS_REGISTRO["email"], password: str = DATOS_REGISTRO["password"]):
    return client.post("/auth/login", json={"email": email, "password": password})


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
