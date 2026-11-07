from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del servicio, leida de variables de entorno."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str

    # Servicio de ventas (red interna): recibe el inventario al publicar.
    ventas_url: str = "http://ventas:8003"
    ventas_timeout_segundos: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
