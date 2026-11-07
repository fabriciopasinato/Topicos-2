"""Cliente HTTP real hacia ventas: exito, error y timeout."""

import httpx
import pytest

from app.cliente_ventas import ClienteVentas, VentasNoDisponible


def _cliente(handler) -> ClienteVentas:
    return ClienteVentas("http://ventas:8003", 2.0, transport=httpx.MockTransport(handler))


def test_envia_el_inventario_al_endpoint_interno():
    recibidos = []

    def handler(request):
        recibidos.append((request.url.path, request.read()))
        return httpx.Response(200, json={"ok": True})

    _cliente(handler).enviar_inventario({"evento_id": 1, "zonas": []})
    assert recibidos[0][0] == "/internal/inventario"


def test_error_de_ventas_se_informa():
    with pytest.raises(VentasNoDisponible):
        _cliente(lambda r: httpx.Response(500)).enviar_inventario({"evento_id": 1, "zonas": []})


def test_timeout_se_informa():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(VentasNoDisponible):
        _cliente(handler).enviar_inventario({"evento_id": 1, "zonas": []})


def test_ventas_inalcanzable_se_informa():
    with pytest.raises(VentasNoDisponible):
        ClienteVentas("http://127.0.0.1:1", 0.5).enviar_inventario({"evento_id": 1, "zonas": []})
