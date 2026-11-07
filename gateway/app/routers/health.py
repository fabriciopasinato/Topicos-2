from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    """200 solo si gateway_db y Redis responden; si no, 503 (unhealthy)."""
    estado = request.app.state
    try:
        async with estado.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="gateway_db no disponible")
    try:
        await estado.redis.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="redis no disponible")
    return {"status": "ok"}
