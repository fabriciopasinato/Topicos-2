from fastapi import FastAPI

from app.routers import eventos, health

app = FastAPI(title="eventos")
app.include_router(health.router)
app.include_router(eventos.router)
