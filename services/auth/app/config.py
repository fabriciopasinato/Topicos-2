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

    # Redis compartido con el gateway: auth ESCRIBE las marcas revocado:<user_id>.
    redis_url: str = "redis://redis:6379/0"

    # Envio de emails (en desarrollo, el contenedor mailpit).
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_tls: bool = False
    email_from: str = "no-reply@ticketera.local"
    # Base de los links que van en los emails.
    frontend_url: str = "http://localhost:3000"

    # Seguridad de cuentas
    intentos_maximos: int = 5
    verificacion_ttl_horas: int = 24
    restablecimiento_ttl_minutos: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
