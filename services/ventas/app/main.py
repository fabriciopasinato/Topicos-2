from fastapi import FastAPI

from app.routers import health, ventas

app = FastAPI(title="ventas")
app.include_router(health.router)
app.include_router(ventas.router)
