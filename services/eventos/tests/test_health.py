from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app


def test_health_con_base_caida_responde_503():
    # Puerto 1 en localhost: nadie escucha, la conexion falla al instante.
    engine = create_engine(
        "postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 1}
    )

    def sesion_sin_base():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sesion_sin_base
    try:
        response = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 503
