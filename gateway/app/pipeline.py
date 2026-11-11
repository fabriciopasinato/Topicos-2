"""Pipeline que el gateway aplica a cada solicitud, en este orden:

1. inicia el timer y toma la IP del cliente
2. descarta X-User-Id / X-User-Role enviados por el cliente
3. rate limit en Redis (antes de llamar a cualquier servicio)
4. valida el JWT localmente (sin llamar a auth) y que no este revocado
5. reenvia al servicio (proxy.py) con la identidad del token
6. registra la solicitud en la bitacora
7. devuelve la respuesta

/health es un endpoint de infraestructura (lo consulta Docker cada pocos
segundos): no pasa por rate limit ni se registra en la bitacora.
"""

import sys
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from app import bitacora, rate_limit, revocacion
from app.seguridad import HEADERS_DE_IDENTIDAD, TokenInvalido, es_publica, validar_token


async def pipeline(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)

    # 1. Timer e IP
    t0 = time.perf_counter()
    ip = request.client.host if request.client else "desconocida"
    metodo = request.method
    ruta = request.url.path

    # 2. Nunca se confia en la identidad que manda el cliente
    request.scope["headers"] = [
        (k, v) for k, v in request.scope["headers"] if k.lower() not in HEADERS_DE_IDENTIDAD
    ]

    estado = request.app.state
    settings = estado.settings
    user_id = None
    try:
        respuesta = await _procesar(request, call_next, estado, settings, ip, metodo, ruta)
        identidad = getattr(request.state, "identidad", None)
        user_id = identidad.user_id if identidad else None
    except Exception:
        respuesta = JSONResponse({"detail": "error interno del gateway"}, status_code=500)

    # 6. Bitacora (antes de responder)
    await bitacora.registrar(
        estado.engine,
        {
            "ip": ip,
            "metodo": metodo,
            "ruta": ruta[:500],
            "user_id": user_id,
            "status": respuesta.status_code,
            "duracion_ms": (time.perf_counter() - t0) * 1000,
        },
        settings.bitacora_timeout_segundos,
    )
    # 7. Respuesta
    return respuesta


async def _procesar(request, call_next, estado, settings, ip, metodo, ruta):
    # 3. Rate limit (fail-open si Redis no responde)
    if metodo != "OPTIONS":
        grupo = rate_limit.grupo_de(metodo, ruta)
        try:
            retry_after = await rate_limit.consumir(
                estado.redis, grupo, ip, rate_limit.limite_de(grupo, settings)
            )
        except Exception as error:  # noqa: BLE001
            print(f"WARNING rate limit sin Redis ({type(error).__name__}): se deja pasar",
                  file=sys.stdout, flush=True)
            retry_after = None
        if retry_after is not None:
            return JSONResponse(
                {"detail": "demasiadas solicitudes"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

    # 4. JWT local
    autorizacion = request.headers.get("authorization", "")
    if autorizacion.lower().startswith("bearer "):
        try:
            identidad = validar_token(autorizacion[7:].strip(), settings.jwt_secret)
        except TokenInvalido:
            return JSONResponse({"detail": "token invalido o expirado"}, status_code=401)
        # 4b. Revocacion inmediata (marca publicada por auth en Redis)
        if await revocacion.esta_revocado(estado.redis, identidad):
            return JSONResponse({"detail": "la sesion fue revocada"}, status_code=401)
        request.state.identidad = identidad
    elif not es_publica(metodo, ruta) and ruta.startswith("/api/"):
        return JSONResponse({"detail": "se requiere autenticacion"}, status_code=401)

    # 5. Reenvio al servicio
    return await call_next(request)
