"""Reenvio de /api/<servicio>/... al microservicio correspondiente.

/api/auth/login       -> auth:    /auth/login
/api/eventos/1        -> eventos: /eventos/1
/api/ventas/reservas  -> ventas:  /ventas/reservas

Solo se reenvian esos tres prefijos: las rutas /internal/* de los servicios
no son alcanzables desde afuera.
"""

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

router = APIRouter()

# Headers que no se copian entre una conexion y otra.
_HOP_BY_HOP = {
    "host",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "content-length",
    "content-encoding",
    "upgrade",
    "authorization",  # los servicios reciben la identidad por X-User-*, no el token
    "x-user-id",
    "x-user-role",
}


@router.api_route(
    "/api/{servicio}/{resto:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
@router.api_route(
    "/api/{servicio}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def reenviar(servicio: str, request: Request, resto: str = "") -> Response:
    settings = request.app.state.settings
    base = settings.servicios().get(servicio)
    if base is None:
        return JSONResponse({"detail": "ruta inexistente"}, status_code=404)

    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
    identidad = getattr(request.state, "identidad", None)
    if identidad is not None:
        headers["X-User-Id"] = identidad.user_id
        headers["X-User-Role"] = identidad.rol

    destino = f"/{servicio}/{resto}" if resto else f"/{servicio}"
    cliente: httpx.AsyncClient = request.app.state.http
    try:
        respuesta = await cliente.request(
            request.method,
            f"{base}{destino}",
            params=request.query_params.multi_items(),
            headers=headers,
            content=await request.body(),
            timeout=settings.proxy_timeout_segundos,
        )
    except httpx.HTTPError:
        return JSONResponse(
            {"detail": f"el servicio '{servicio}' no esta disponible"}, status_code=503
        )

    headers_respuesta = {
        k: v for k, v in respuesta.headers.items() if k.lower() not in _HOP_BY_HOP
    }
    return Response(
        content=respuesta.content,
        status_code=respuesta.status_code,
        headers=headers_respuesta,
    )
