from contextlib import asynccontextmanager

import httpx
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.db import crear_engine
from app.pipeline import pipeline
from app.routers import health
from app import proxy


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Fabrica de la app. Los clientes (base, Redis, HTTP) se crean en el
    lifespan, dentro del event loop que atiende las requests.

    `transport` permite a los tests reemplazar los microservicios reales.
    """
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.engine = crear_engine(settings.database_url)
        app.state.redis = redis.from_url(
            settings.redis_url, socket_connect_timeout=1, socket_timeout=1
        )
        app.state.http = httpx.AsyncClient(transport=transport)
        yield
        await app.state.http.aclose()
        await app.state.redis.aclose()
        await app.state.engine.dispose()

    app = FastAPI(title="gateway", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(proxy.router)

    # CORS queda "adentro" del pipeline: el pipeline (agregado despues) es la
    # capa externa, asi tambien los preflight quedan en la bitacora.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.lista_cors(),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["Retry-After"],
    )
    app.middleware("http")(pipeline)
    return app
