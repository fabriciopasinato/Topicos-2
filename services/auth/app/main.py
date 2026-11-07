from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import servicio
from app.config import get_settings
from app.db import get_engine
from app.routers import auth, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed idempotente del administrador inicial (las migraciones ya corrieron).
    settings = get_settings()
    with Session(get_engine()) as session:
        servicio.crear_admin_inicial(session, settings.admin_email, settings.admin_password)
    yield


app = FastAPI(title="auth", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
