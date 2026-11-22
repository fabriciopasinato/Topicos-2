"""Cliente HTTP sync hacia ventas."""

from datetime import datetime

import httpx

from app.config import get_settings


class VentasNoDisponible(Exception):
    pass


class InventarioInexistente(VentasNoDisponible):
    """404 de ventas. No deberia pasar con un evento publicado; se reintenta igual."""


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

    def actualizar_evento(self, evento_id: int, version: int, fecha_inicio: datetime | None = None,
                          cancelado: bool = False) -> None:
        cuerpo: dict = {"version": version}
        if fecha_inicio is not None:
            cuerpo["fecha_inicio"] = fecha_inicio.isoformat()
        if cancelado:
            cuerpo["cancelado"] = True
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as http:
                r = http.put(f"{self.base_url}/internal/eventos/{evento_id}", json=cuerpo)
        except httpx.HTTPError as error:
            raise VentasNoDisponible(str(error)) from error
        if r.status_code == 404:
            raise InventarioInexistente(f"ventas no tiene el inventario del evento {evento_id}")
        if r.status_code >= 300:
            raise VentasNoDisponible(f"ventas respondio {r.status_code}")


def get_cliente_ventas() -> ClienteVentas:
    s = get_settings()
    return ClienteVentas(s.ventas_url, s.ventas_timeout_segundos)
