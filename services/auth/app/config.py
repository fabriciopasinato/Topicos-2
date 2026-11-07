from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del servicio, leida de variables de entorno."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str

    # Mismo secreto que el gateway. Obligatorio: sin valor por defecto.
    jwt_secret: str
    jwt_access_ttl_minutes: int = 120
    jwt_refresh_ttl_days: int = 7

    # Administrador inicial (seed idempotente). Si falta alguno, no se crea.
    admin_email: str | None = None
    admin_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
