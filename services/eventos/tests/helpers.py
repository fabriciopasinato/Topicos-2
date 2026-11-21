"""Datos comunes a los tests de eventos."""

from datetime import UTC, datetime, timedelta


def fecha_futura(dias: int = 30) -> str:
    """Fecha ISO `dias` despues de ahora. Relativa a proposito: con una fecha
    fija, los tests empezarian a fallar solos el dia que esa fecha pase (el
    evento se informaria finalizado y no se podria publicar)."""
    return (datetime.now(UTC) + timedelta(days=dias)).isoformat()


def datos_evento(recinto_id: int, **cambios) -> dict:
    """Cuerpo valido de POST /eventos; `cambios` pisa o agrega campos."""
    return {
        "nombre": "Recital",
        "fecha": fecha_futura(),
        "recinto_id": recinto_id,
        "tipo": "recital",
        "organizador": "DF Entertainment",
        **cambios,
    }


class VentasFalsa:
    """Reemplaza al cliente HTTP de ventas aplicando sus mismas reglas: solo
    versiones mayores a la ultima, y la cancelacion es irreversible. Asi los
    tests pueden verificar el estado final en los dos servicios.
    `caida = True` simula ventas sin responder."""

    def __init__(self):
        import threading

        self.caida = False
        self.inventarios: list[dict] = []
        self.eventos: dict[int, dict] = {}  # evento_id -> {version, fecha_inicio, cancelado}
        self.recibidos: list[dict] = []
        self._lock = threading.Lock()

    def _no_responde(self):
        from app.cliente_ventas import VentasNoDisponible

        if self.caida:
            raise VentasNoDisponible("timeout")

    def enviar_inventario(self, inventario: dict) -> None:
        self._no_responde()
        with self._lock:
            self.inventarios.append(inventario)
            self.eventos.setdefault(inventario["evento_id"], {
                "version": 0, "fecha_inicio": inventario.get("fecha_inicio"), "cancelado": False,
            })

    def actualizar_evento(self, evento_id, version, fecha_inicio=None, cancelado=False) -> None:
        self._no_responde()
        if fecha_inicio is not None:
            fecha_inicio = fecha_inicio.isoformat()  # como viaja por la red (JSON)
        with self._lock:
            self.recibidos.append({"evento_id": evento_id, "version": version,
                                   "fecha_inicio": fecha_inicio, "cancelado": cancelado})
            estado = self.eventos.setdefault(evento_id, {"version": 0, "fecha_inicio": None, "cancelado": False})
            if version > estado["version"]:
                estado["version"] = version
                if cancelado:
                    estado["cancelado"] = True
                elif fecha_inicio is not None and not estado["cancelado"]:
                    estado["fecha_inicio"] = fecha_inicio
