"""6.3 Cartelera publica y 6.4 publicacion con entrega de inventario a ventas."""

import pytest

from app.cliente_ventas import VentasNoDisponible, get_cliente_ventas
from app.main import app

OWNER = {"X-User-Id": "10", "X-User-Role": "event_owner"}
CLIENTE = {"X-User-Id": "20", "X-User-Role": "cliente"}


class VentasFalso:
    """Reemplaza al cliente HTTP de ventas. Registra lo que recibe."""

    def __init__(self):
        self.recibidos: list[dict] = []
        self.caido = False

    def enviar_inventario(self, inventario: dict) -> None:
        if self.caido:
            raise VentasNoDisponible("timeout")
        self.recibidos.append(inventario)


@pytest.fixture
def ventas(client):
    falso = VentasFalso()
    app.dependency_overrides[get_cliente_ventas] = lambda: falso
    return falso


@pytest.fixture
def evento(client):
    recinto = client.post("/eventos/recintos", json={"nombre": "Estadio"}, headers=OWNER).json()
    ev = client.post("/eventos", json={"nombre": "Recital", "fecha": "2026-12-20T21:00:00Z",
                                       "recinto_id": recinto["id"]}, headers=OWNER).json()
    return ev


@pytest.fixture
def evento_con_zonas(client, evento):
    sector = client.post(f"/eventos/{evento['id']}/sectores", json={"nombre": "Platea"}, headers=OWNER).json()
    base = f"/eventos/{evento['id']}/sectores/{sector['id']}/zonas"
    client.post(base, json={"nombre": "Platea A", "tipo": "numerada", "precio": "1500",
                            "filas": ["A", "B"], "asientos_por_fila": 3}, headers=OWNER)
    client.post(base, json={"nombre": "Campo", "tipo": "general", "precio": "800", "capacidad": 500}, headers=OWNER)
    return evento


def _publicar(client, evento):
    return client.post(f"/eventos/{evento['id']}/publicar", headers=OWNER)


# --- 6.3 Cartelera ----------------------------------------------------------
def test_cartelera_publica_muestra_solo_publicados(client, evento_con_zonas, ventas, evento):
    assert client.get("/eventos").json() == []
    _publicar(client, evento_con_zonas)
    cartelera = client.get("/eventos").json()
    assert [e["nombre"] for e in cartelera] == ["Recital"]


def test_borrador_ajeno_responde_404(client, evento):
    assert client.get(f"/eventos/{evento['id']}", headers=CLIENTE).status_code == 404
    assert client.get(f"/eventos/{evento['id']}").status_code == 404
    assert client.get(f"/eventos/{evento['id']}", headers=OWNER).status_code == 200


def test_detalle_no_incluye_disponibilidad(client, evento_con_zonas, ventas):
    _publicar(client, evento_con_zonas)
    detalle = client.get(f"/eventos/{evento_con_zonas['id']}").json()
    zonas = [z for s in detalle["sectores"] for z in s["zonas"]]
    texto = str(detalle).lower()
    assert zonas and all("precio" in z for z in zonas)
    assert not any(palabra in texto for palabra in ("vendido", "disponible", "reservado"))


# --- 6.4 Publicacion -----------------------------------------------------------
def test_publicacion_exitosa_entrega_inventario(client, evento_con_zonas, ventas):
    r = _publicar(client, evento_con_zonas)
    assert r.status_code == 200 and r.json()["estado"] == "publicado"
    [inventario] = ventas.recibidos
    assert inventario["evento_id"] == evento_con_zonas["id"]
    numerada = next(z for z in inventario["zonas"] if z["tipo"] == "numerada")
    general = next(z for z in inventario["zonas"] if z["tipo"] == "general")
    assert len(numerada["asientos"]) == 6 and numerada["precio"] == "1500.00"
    assert general["capacidad"] == 500


def test_ventas_caido_deja_el_evento_en_borrador(client, evento_con_zonas, ventas):
    ventas.caido = True
    r = _publicar(client, evento_con_zonas)
    assert r.status_code == 503
    assert client.get(f"/eventos/{evento_con_zonas['id']}", headers=OWNER).json()["estado"] == "borrador"


def test_reintento_tras_timeout_publica(client, evento_con_zonas, ventas):
    ventas.caido = True
    _publicar(client, evento_con_zonas)
    ventas.caido = False
    r = _publicar(client, evento_con_zonas)
    assert r.status_code == 200 and r.json()["estado"] == "publicado"


def test_publicar_dos_veces_no_reenvia_el_inventario(client, evento_con_zonas, ventas):
    _publicar(client, evento_con_zonas)
    r = _publicar(client, evento_con_zonas)
    assert r.status_code == 200
    assert len(ventas.recibidos) == 1


def test_publicacion_sin_zonas_responde_422(client, evento, ventas):
    r = _publicar(client, evento)
    assert r.status_code == 422
    assert ventas.recibidos == []


def test_zonas_publicadas_no_se_pueden_modificar(client, evento_con_zonas, ventas):
    _publicar(client, evento_con_zonas)
    detalle = client.get(f"/eventos/{evento_con_zonas['id']}").json()
    sector = detalle["sectores"][0]
    zona_id = sector["zonas"][0]["id"]

    assert client.delete(f"/eventos/{evento_con_zonas['id']}/zonas/{zona_id}", headers=OWNER).status_code == 409
    nueva = {"nombre": "Extra", "tipo": "general", "precio": "1", "capacidad": 5}
    r = client.post(f"/eventos/{evento_con_zonas['id']}/sectores/{sector['id']}/zonas", json=nueva, headers=OWNER)
    assert r.status_code == 409


def test_cliente_no_puede_publicar(client, evento_con_zonas, ventas):
    assert client.post(f"/eventos/{evento_con_zonas['id']}/publicar", headers=CLIENTE).status_code == 403
