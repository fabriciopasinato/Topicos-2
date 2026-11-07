"""Cliente HTTP sync hacia ventas. Unica llamada entre microservicios de la
Etapa I: al publicar un evento se le entrega el inventario."""

import httpx

from app.config import get_settings


class VentasNoDisponible(Exception):
    pass


class ClienteVentas:
    def __init__(self, base_url: str, timeout: float, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url
        self.timeout = timeout
        self.transport = transport

    def enviar_inventario(self, inventario: dict) -> None:
        """POST /internal/inventario. Idempotente del lado de ventas."""
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as http:
                r = http.post(f"{self.base_url}/internal/inventario", json=inventario)
        except httpx.HTTPError as error:
            raise VentasNoDisponible(str(error)) from error
        if r.status_code >= 300:
            raise VentasNoDisponible(f"ventas respondio {r.status_code}")


def get_cliente_ventas() -> ClienteVentas:
    s = get_settings()
    return ClienteVentas(s.ventas_url, s.ventas_timeout_segundos)
