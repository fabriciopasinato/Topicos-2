from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# Puerto 1 en localhost: nadie escucha, la conexion falla al instante.
BASE_CAIDA = "postgresql+asyncpg://x:x@127.0.0.1:1/x"
REDIS_CAIDO = "redis://127.0.0.1:1/0"


def test_health_con_base_y_redis_caidos_responde_503():
    app = create_app(Settings(database_url=BASE_CAIDA, redis_url=REDIS_CAIDO, jwt_secret="s"))
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 503
