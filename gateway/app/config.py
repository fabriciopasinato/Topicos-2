from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion del gateway, leida de variables de entorno."""

    model_config = SettingsConfigDict(extra="ignore")

    # postgresql+asyncpg://... (la app es async; Alembic usa la variante sync)
    database_url: str
    redis_url: str

    # Microservicios internos (red de Compose)
    auth_url: str = "http://auth:8001"
    eventos_url: str = "http://eventos:8002"
    ventas_url: str = "http://ventas:8003"
    proxy_timeout_segundos: float = 5.0

    # JWT de acceso (mismo secreto que auth). Obligatorio: sin valor por defecto.
    jwt_secret: str

    # Rate limit por IP y por minuto, segun grupo de rutas
    rate_limit_auth: int = 10
    rate_limit_compra: int = 20
    rate_limit_general: int = 100

    # Bitacora: tiempo maximo para escribir el registro antes de responder
    bitacora_timeout_segundos: float = 0.5

    # Origenes permitidos para CORS, separados por coma
    cors_origins: str = ""

    def servicios(self) -> dict[str, str]:
        return {"auth": self.auth_url, "eventos": self.eventos_url, "ventas": self.ventas_url}

    def lista_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def sync_database_url(url: str) -> str:
    """URL equivalente con driver sync, para Alembic."""
    return url.replace("+asyncpg", "+psycopg")
