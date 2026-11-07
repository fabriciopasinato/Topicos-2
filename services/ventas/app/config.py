from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del servicio, leida de variables de entorno."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str

    # Una reserva bloquea sus tickets este tiempo o hasta el pago (lo que ocurra primero).
    reserva_ttl_minutes: int = 5
    reserva_max_tickets: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
