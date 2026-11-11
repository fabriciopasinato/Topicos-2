"""Fixtures comunes de tests del gateway.

- Los tests corren SOLO contra una base cuyo nombre termina en "_test".
- El gateway es async y crea su propio engine en el lifespan, por eso no se le
  puede inyectar una transaccion con rollback: cada test arranca con las tablas
  vaciadas (TRUNCATE) y con Redis de test vacio (FLUSHDB).
"""

import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

SERVICIO_DIR = Path(__file__).resolve().parent.parent

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://gateway:gateway_test@localhost:5433/gateway_db_test",
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6380/0")


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

from datetime import datetime, timedelta, timezone  # noqa: E402

import httpx  # noqa: E402
import jwt  # noqa: E402
import redis  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.config import Settings, sync_database_url  # noqa: E402,F401
from app.main import create_app  # noqa: E402

SYNC_URL = sync_database_url(TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def engine_sync():
    """Engine sync para preparar e inspeccionar la base desde los tests."""
    cfg = Config(str(SERVICIO_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICIO_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")
    eng = create_engine(SYNC_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def redis_sync():
    cliente = redis.from_url(TEST_REDIS_URL)
    yield cliente
    cliente.close()


@pytest.fixture(autouse=True)
def ventana_de_rate_limit_fija(monkeypatch):
    """El rate limit usa ventanas por minuto: si un test cruzara el cambio de
    minuto, el contador se reiniciaria a mitad del test. Se fija el reloj del
    rate limit al segundo 1 del proximo minuto (futuro, asi las claves de
    Redis no vencen durante el test)."""
    import time as _time
    from types import SimpleNamespace

    from app import rate_limit

    fijo = (int(_time.time()) // 60 + 1) * 60 + 1
    # Solo se reemplaza la referencia que usa rate_limit, no el modulo time global.
    monkeypatch.setattr(rate_limit, "time", SimpleNamespace(time=lambda: fijo))


@pytest.fixture(autouse=True)
def base_y_redis_limpios(engine_sync, redis_sync):
    """Cada test arranca con todas las tablas vacias y Redis vacio."""
    redis_sync.flushdb()
    yield
    with engine_sync.begin() as conexion:
        tablas = conexion.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).scalars().all()
        if tablas:
            conexion.execute(text(f"TRUNCATE {', '.join(tablas)} RESTART IDENTITY CASCADE"))
    redis_sync.flushdb()


JWT_SECRET_TEST = "secreto-de-test"


def settings_de_test(**cambios) -> Settings:
    base = {
        "database_url": TEST_DATABASE_URL,
        "redis_url": TEST_REDIS_URL,
        "jwt_secret": JWT_SECRET_TEST,
    }
    base.update(cambios)
    return Settings(**base)


def token(sub: str = "7", rol: str = "cliente", minutos: int = 60, secreto: str = JWT_SECRET_TEST,
          iat: int | None = None) -> str:
    """JWT de acceso como los que emite auth (con iat)."""
    ahora = datetime.now(timezone.utc)
    datos = {"sub": sub, "rol": rol, "exp": ahora + timedelta(minutes=minutos),
             "iat": iat if iat is not None else int(ahora.timestamp())}
    return jwt.encode(datos, secreto, algorithm="HS256")


class ServiciosFalsos:
    """Reemplaza a auth/eventos/ventas: responde con lo que recibio y registra
    cada llamada. `caidos` simula servicios detenidos."""

    def __init__(self):
        self.llamadas: list[httpx.Request] = []
        self.caidos: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        servicio = request.url.host
        if servicio in self.caidos:
            raise httpx.ConnectError("servicio detenido", request=request)
        self.llamadas.append(request)
        return httpx.Response(
            200,
            json={
                "servicio": servicio,
                "ruta": request.url.path,
                "query": str(request.url.query, "ascii") if isinstance(request.url.query, bytes) else str(request.url.query),
                "x_user_id": request.headers.get("x-user-id"),
                "x_user_role": request.headers.get("x-user-role"),
                "authorization": request.headers.get("authorization"),
            },
        )


@pytest.fixture
def servicios() -> ServiciosFalsos:
    return ServiciosFalsos()


@pytest.fixture
def crear_gateway(servicios):
    """Fabrica de TestClients del gateway con servicios falsos."""
    abiertos = []

    def _crear(**cambios):
        c = TestClient(create_app(settings_de_test(**cambios), transport=httpx.MockTransport(servicios)))
        c.__enter__()
        abiertos.append(c)
        return c

    yield _crear
    for c in abiertos:
        c.__exit__(None, None, None)


@pytest.fixture
def client(crear_gateway):
    return crear_gateway()


def filas_bitacora(engine_sync) -> list[dict]:
    with engine_sync.connect() as conexion:
        return [
            dict(f._mapping)
            for f in conexion.execute(text("SELECT * FROM bitacora ORDER BY id"))
        ]
