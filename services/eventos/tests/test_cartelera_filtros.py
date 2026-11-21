"""Cartelera: filtros por tipo y fecha, exclusion de cancelados y finalizados,
y visibilidad del detalle de eventos cancelados."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.helpers import datos_evento

OWNER = {"X-User-Id": "10", "X-User-Role": "event_owner"}
CLIENTE = {"X-User-Id": "20", "X-User-Role": "cliente"}


@pytest.fixture
def recinto(client):
    return client.post("/eventos/recintos", json={"nombre": "Estadio"}, headers=OWNER).json()["id"]


@pytest.fixture
def crear(client, db_session, recinto):
    """Crea un evento y lo deja en el estado y la fecha pedidos (por SQL, para
    no depender de ventas). `dias` negativo = fecha pasada."""

    def _crear(nombre: str, estado: str = "publicado", dias: float = 30, tipo: str = "recital",
               publicado: bool | None = None) -> int:
        evento_id = client.post("/eventos", json=datos_evento(recinto, nombre=nombre, tipo=tipo), headers=OWNER).json()["id"]
        publicado = estado == "publicado" if publicado is None else publicado
        db_session.execute(
            text("UPDATE eventos SET estado = :s, fecha = now() + make_interval(secs => :seg), "
                 "publicado_at = CASE WHEN :p THEN now() END WHERE id = :e"),
            {"s": estado, "seg": dias * 86400, "p": publicado, "e": evento_id},
        )
        db_session.expire_all()
        return evento_id

    return _crear


def _cartelera(client, **filtros) -> list[str]:
    r = client.get("/eventos", params=filtros)
    assert r.status_code == 200, r.text
    return [e["nombre"] for e in r.json()]


def _iso(dias: float) -> str:
    return (datetime.now(UTC) + timedelta(days=dias)).isoformat()


# --- Listado -----------------------------------------------------------------------

def test_cancelados_y_finalizados_fuera_del_listado(client, crear):
    crear("Vigente")
    crear("Cancelado", estado="cancelado", publicado=True)
    crear("Finalizado", dias=-0.05)  # empezo hace ~1 hora
    crear("Borrador", estado="borrador")
    assert _cartelera(client) == ["Vigente"]


def test_listado_ordenado_por_fecha(client, crear):
    crear("Despues", dias=20)
    crear("Antes", dias=10)
    assert _cartelera(client) == ["Antes", "Despues"]


def test_filtro_por_tipo(client, crear):
    crear("Recital", tipo="recital")
    crear("Obra", tipo="teatro")
    assert _cartelera(client, tipo="recital") == ["Recital"]


def test_filtro_por_rango_de_fechas(client, crear):
    crear("Semana 1", dias=7)
    crear("Semana 3", dias=21)
    crear("Semana 6", dias=42)
    assert _cartelera(client, desde=_iso(14), hasta=_iso(30)) == ["Semana 3"]
    assert _cartelera(client, desde=_iso(14)) == ["Semana 3", "Semana 6"]
    assert _cartelera(client, hasta=_iso(14)) == ["Semana 1"]


def test_filtros_combinados(client, crear):
    crear("Recital cerca", dias=7, tipo="recital")
    crear("Obra cerca", dias=7, tipo="teatro")
    crear("Recital lejos", dias=42, tipo="recital")
    assert _cartelera(client, tipo="recital", hasta=_iso(14)) == ["Recital cerca"]


@pytest.mark.parametrize("filtros", [
    {"tipo": "stand-up"},
    {"desde": _iso(30), "hasta": _iso(10)},
    {"desde": "no-es-una-fecha"},
])
def test_filtro_invalido_responde_422(client, filtros):
    assert client.get("/eventos", params=filtros).status_code == 422


# --- Detalle de cancelados ---------------------------------------------------------

def test_detalle_publico_de_un_evento_cancelado_tras_publicarse(client, crear):
    evento_id = crear("Cancelado", estado="cancelado", publicado=True)
    r = client.get(f"/eventos/{evento_id}")
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"


def test_borrador_cancelado_responde_404_al_publico(client, crear):
    evento_id = crear("Borrador cancelado", estado="cancelado", publicado=False)
    assert client.get(f"/eventos/{evento_id}").status_code == 404
    assert client.get(f"/eventos/{evento_id}", headers=CLIENTE).status_code == 404
    assert client.get(f"/eventos/{evento_id}", headers=OWNER).status_code == 200


def test_detalle_publico_de_un_evento_finalizado(client, crear):
    evento_id = crear("Finalizado", dias=-0.05)
    r = client.get(f"/eventos/{evento_id}")
    assert r.status_code == 200 and r.json()["estado"] == "finalizado"
