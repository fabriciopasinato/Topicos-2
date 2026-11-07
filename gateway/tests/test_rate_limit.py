"""4.4 Rate limit por IP en Redis, por grupo de rutas."""

import asyncio
import time

import redis.asyncio as aioredis

from app import rate_limit
from app.config import Settings
from tests.conftest import TEST_REDIS_URL, token


def test_limite_general_rechaza_la_solicitud_101(client, servicios):
    for _ in range(100):
        assert client.get("/api/eventos").status_code == 200
    r = client.get("/api/eventos")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    assert len(servicios.llamadas) == 100  # la 101 no llego al servicio


def test_limite_estricto_en_login(crear_gateway, servicios):
    client = crear_gateway(rate_limit_auth=3)
    for _ in range(3):
        assert client.post("/api/auth/login", json={}).status_code == 200
    r = client.post("/api/auth/login", json={})
    assert r.status_code == 429 and "Retry-After" in r.headers
    assert len(servicios.llamadas) == 3


def test_limite_estricto_en_registro(crear_gateway):
    client = crear_gateway(rate_limit_auth=2)
    client.post("/api/auth/registro", json={})
    client.post("/api/auth/registro", json={})
    r = client.post("/api/auth/registro", json={})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_limite_estricto_en_compra(crear_gateway, servicios):
    client = crear_gateway(rate_limit_compra=2)
    auth = {"Authorization": f"Bearer {token()}"}
    assert client.post("/api/ventas/reservas", json={}, headers=auth).status_code == 200
    assert client.post("/api/ventas/reservas/1/pago", headers=auth).status_code == 200
    r = client.delete("/api/ventas/reservas/1", headers=auth)
    assert r.status_code == 429 and "Retry-After" in r.headers
    assert len(servicios.llamadas) == 2


def test_grupos_independientes(crear_gateway):
    client = crear_gateway(rate_limit_auth=1)
    client.post("/api/auth/login", json={})
    assert client.post("/api/auth/login", json={}).status_code == 429
    assert client.get("/api/eventos").status_code == 200


def test_retry_after_es_el_tiempo_restante_de_la_ventana():
    async def escenario():
        cliente = aioredis.from_url(TEST_REDIS_URL)
        # Comienzo exacto de la proxima ventana (en el futuro, para que la
        # expiracion de la clave no la borre al instante).
        inicio = (int(time.time()) // 60 + 1) * 60
        ahora = inicio + 40  # faltan 20 segundos
        try:
            assert await rate_limit.consumir(cliente, "general", "1.2.3.4", 1, ahora) is None
            retry = await rate_limit.consumir(cliente, "general", "1.2.3.4", 1, ahora)
        finally:
            await cliente.aclose()
        return retry

    retry = asyncio.run(escenario())
    assert retry == 20


def test_contadores_compartidos_entre_dos_instancias(crear_gateway):
    a = crear_gateway(rate_limit_general=4)
    b = crear_gateway(rate_limit_general=4)
    codigos = [c.get("/api/eventos").status_code for c in (a, b, a, b, a)]
    assert codigos == [200, 200, 200, 200, 429]


def test_limites_configurables_por_variables_de_entorno(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_AUTH", "3")
    monkeypatch.setenv("RATE_LIMIT_COMPRA", "4")
    monkeypatch.setenv("RATE_LIMIT_GENERAL", "50")
    s = Settings(database_url="postgresql+asyncpg://x/y_test", redis_url="redis://x", jwt_secret="s")
    assert (s.rate_limit_auth, s.rate_limit_compra, s.rate_limit_general) == (3, 4, 50)


def test_redis_caido_deja_pasar_las_solicitudes(crear_gateway, capsys):
    client = crear_gateway(redis_url="redis://127.0.0.1:1/0")
    assert client.get("/api/eventos").status_code == 200
    assert "rate limit sin Redis" in capsys.readouterr().out
