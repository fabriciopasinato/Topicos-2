from logging.config import fileConfig

from sqlalchemy import create_engine

from alembic import context
from app import models  # noqa: F401  (registra los modelos en Base.metadata)
from app.config import Settings, sync_database_url
from app.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    # Permite que los tests pasen la URL de la base de test por config.
    url = config.get_main_option("sqlalchemy.url") or Settings().database_url
    return sync_database_url(url)


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
