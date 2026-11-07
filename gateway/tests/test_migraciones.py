from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from tests.conftest import SERVICIO_DIR, TEST_DATABASE_URL


def _config() -> Config:
    cfg = Config(str(SERVICIO_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICIO_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


def test_migracion_crea_y_elimina_bitacora(engine_sync):
    cfg = _config()
    try:
        command.downgrade(cfg, "base")
        assert "bitacora" not in inspect(engine_sync).get_table_names()

        command.upgrade(cfg, "head")
        columnas = {c["name"] for c in inspect(engine_sync).get_columns("bitacora")}
        assert {"ip", "metodo", "ruta", "user_id", "status", "duracion_ms"} <= columnas
    finally:
        command.upgrade(cfg, "head")
