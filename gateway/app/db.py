from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def crear_engine(database_url: str) -> AsyncEngine:
    # pool_pre_ping: tras un reinicio de PostgreSQL descarta conexiones muertas.
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"timeout": 3},
    )
