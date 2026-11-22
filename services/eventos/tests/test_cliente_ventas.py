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


# --- Actualizacion versionada del evento (reprogramacion / cancelacion) ---------

from datetime import UTC, datetime  # noqa: E402

from app.cliente_ventas import InventarioInexistente  # noqa: E402


def test_envia_la_reprogramacion_con_su_version():
    recibidos = []

    def handler(request):
        recibidos.append((request.method, request.url.path, request.read()))
        return httpx.Response(200, json={"aplicado": True})

    _cliente(handler).actualizar_evento(7, 3, fecha_inicio=datetime(2030, 1, 3, 21, tzinfo=UTC))
    metodo, ruta, cuerpo = recibidos[0]
    assert (metodo, ruta) == ("PUT", "/internal/eventos/7")
    assert httpx.Response(200, content=cuerpo).json() == {"version": 3, "fecha_inicio": "2030-01-03T21:00:00+00:00"}


def test_envia_la_cancelacion_con_su_version():
    cuerpos = []

    def handler(request):
        cuerpos.append(httpx.Response(200, content=request.read()).json())
        return httpx.Response(200, json={"aplicado": False})  # ignorada por version: tambien es exito

    _cliente(handler).actualizar_evento(7, 4, cancelado=True)
    assert cuerpos == [{"version": 4, "cancelado": True}]


def test_actualizacion_con_timeout_se_informa():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(VentasNoDisponible):
        _cliente(handler).actualizar_evento(7, 2, cancelado=True)


def test_actualizacion_con_error_5xx_se_informa():
    with pytest.raises(VentasNoDisponible):
        _cliente(lambda r: httpx.Response(503)).actualizar_evento(7, 2, cancelado=True)


def test_actualizacion_de_evento_sin_inventario_se_distingue():
    with pytest.raises(InventarioInexistente) as error:
        _cliente(lambda r: httpx.Response(404)).actualizar_evento(7, 2, cancelado=True)
    assert isinstance(error.value, VentasNoDisponible)  # se reintenta como cualquier fallo
