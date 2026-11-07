"""Datos y utilidades comunes a los tests de ventas."""

import uuid

EVENTO = 1
ZONA_NUMERADA = 10
ZONA_GENERAL = 20

CLIENTE = {"X-User-Id": "20", "X-User-Role": "cliente"}
OTRO_CLIENTE = {"X-User-Id": "21", "X-User-Role": "cliente"}
OWNER = {"X-User-Id": "10", "X-User-Role": "event_owner"}


def inventario(evento_id: int = EVENTO, filas=("A", "B", "C"), por_fila: int = 10, capacidad_general: int = 10) -> dict:
    return {
        "evento_id": evento_id,
        "zonas": [
            {"zona_id": ZONA_NUMERADA, "tipo": "numerada", "precio": "1500.00",
             "asientos": [{"fila": f, "numero": n} for f in filas for n in range(1, por_fila + 1)]},
            {"zona_id": ZONA_GENERAL, "tipo": "general", "precio": "800.00", "capacidad": capacidad_general},
        ],
    }


def disponibilidad(client, evento_id: int = EVENTO) -> dict:
    return {z["zona_id"]: z for z in client.get(f"/ventas/eventos/{evento_id}/disponibilidad").json()["zonas"]}


def asiento(client, nombre: str, evento_id: int = EVENTO) -> dict:
    """'A-5' -> {'ticket_id':..., 'disponible':...}"""
    fila, numero = nombre.split("-")
    for a in disponibilidad(client, evento_id)[ZONA_NUMERADA]["asientos"]:
        if a["fila"] == fila and a["numero"] == int(numero):
            return a
    raise KeyError(nombre)


def con_clave(headers: dict, clave: str | None = None) -> dict:
    return {**headers, "Idempotency-Key": clave or str(uuid.uuid4())}


def reservar(client, asientos=(), generales=(), headers=CLIENTE, clave=None, evento_id: int = EVENTO):
    """`asientos` como nombres ('A-1') y `generales` como [(zona_id, cantidad)]."""
    ids = [asiento(client, a, evento_id)["ticket_id"] for a in asientos]
    cuerpo = {"evento_id": evento_id, "asientos": ids,
              "generales": [{"zona_id": z, "cantidad": c} for z, c in generales]}
    return client.post("/ventas/reservas", json=cuerpo, headers=con_clave(headers, clave))
