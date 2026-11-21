"""eventos-cron. Usa commits reales: el cron abre sus propias transacciones."""

import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import cron, servicio
from app.identidad import Identidad
from app.schemas import EventoIn
from tests.helpers import VentasFalsa

pytestmark = pytest.mark.concurrencia

OWNER = Identidad(user_id=10, rol="event_owner")


@pytest.fixture
def ventas():
    return VentasFalsa()


@pytest.fixture
def nuevo_evento(db_concurrente, ventas):
    """Crea eventos publicados con commits reales; ventas falsa tiene su inventario."""

    def _nuevo() -> int:
        with Session(db_concurrente) as s:
            recinto = servicio.crear_recinto(s, "Estadio", "")
            evento = servicio.crear_evento(s, EventoIn(
                nombre="Recital", fecha=datetime.now(UTC) + timedelta(days=30), recinto_id=recinto.id,
                tipo="recital", organizador="DF",
            ), OWNER)
            s.execute(text("UPDATE eventos SET estado = 'publicado', publicado_at = now() WHERE id = :e"),
                      {"e": evento.id})
            s.commit()
            ventas.eventos[evento.id] = {"version": 0, "fecha_inicio": None, "cancelado": False}
            return evento.id

    return _nuevo


def _sesion(engine):
    return lambda: Session(engine)


def _vencer_reintentos(engine) -> None:
    """Hace que las pendientes ya esten para reintentar (sin esperar el backoff)."""
    with engine.begin() as c:
        c.execute(text("UPDATE operaciones_ventas SET proximo_intento_at = now() WHERE estado = 'pendiente'"))


def _fila(engine, sql: str, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).one()


def _pendiente(engine, ventas, evento_id, accion, *args) -> None:
    """Registra una operacion con ventas caida, asi queda pendiente."""
    ventas.caida = True
    with Session(engine) as s:
        assert accion(s, evento_id, OWNER, ventas, *args) == servicio.Resultado.PENDIENTE
    ventas.caida = False


def test_pendiente_confirmada_cuando_ventas_vuelve(db_concurrente, ventas, nuevo_evento):
    evento_id = nuevo_evento()
    _pendiente(db_concurrente, ventas, evento_id, servicio.cancelar)
    _vencer_reintentos(db_concurrente)

    assert cron.ciclo(_sesion(db_concurrente), ventas, lote=20) == 1

    assert _fila(db_concurrente, "SELECT estado FROM eventos WHERE id = :e", e=evento_id) == ("cancelado",)
    assert _fila(db_concurrente, "SELECT estado FROM operaciones_ventas") == ("confirmada",)
    assert ventas.eventos[evento_id]["cancelado"] is True


def test_pendiente_postergada_cuando_ventas_sigue_caido(db_concurrente, ventas, nuevo_evento):
    evento_id = nuevo_evento()
    _pendiente(db_concurrente, ventas, evento_id, servicio.cancelar)  # 1er intento (el inmediato)
    _vencer_reintentos(db_concurrente)
    ventas.caida = True

    assert cron.ciclo(_sesion(db_concurrente), ventas, lote=20) == 1

    estado, intentos, futuro, error = _fila(
        db_concurrente,
        "SELECT estado, intentos, proximo_intento_at > now(), ultimo_error IS NOT NULL FROM operaciones_ventas")
    assert (estado, intentos, futuro, error) == ("pendiente", 2, True, True)
    # Postergada: el ciclo siguiente no la vuelve a intentar antes de tiempo.
    assert cron.ciclo(_sesion(db_concurrente), ventas, lote=20) == 0
    assert _fila(db_concurrente, "SELECT estado FROM eventos WHERE id = :e", e=evento_id) == ("publicado",)


def test_falla_entre_la_confirmacion_de_ventas_y_el_registro_en_eventos(db_concurrente, ventas, nuevo_evento):
    evento_id = nuevo_evento()
    nueva = datetime.now(UTC) + timedelta(days=60)
    _pendiente(db_concurrente, ventas, evento_id, servicio.reprogramar, nueva)
    ventas.actualizar_evento(evento_id, 1, fecha_inicio=nueva)  # ventas ya la tiene
    estado_en_ventas = dict(ventas.eventos[evento_id])
    _vencer_reintentos(db_concurrente)

    cron.ciclo(_sesion(db_concurrente), ventas, lote=20)

    assert ventas.eventos[evento_id] == estado_en_ventas
    assert len([r for r in ventas.recibidos if r["evento_id"] == evento_id]) == 2  # el reenvio llego
    (fecha,) = _fila(db_concurrente, "SELECT fecha FROM eventos WHERE id = :e", e=evento_id)
    assert fecha == nueva


def test_dos_reprogramaciones_pendientes_terminan_con_la_ultima(db_concurrente, ventas, nuevo_evento):
    evento_id = nuevo_evento()
    primera = datetime.now(UTC) + timedelta(days=60)
    ultima = datetime.now(UTC) + timedelta(days=90)
    _pendiente(db_concurrente, ventas, evento_id, servicio.reprogramar, primera)
    _pendiente(db_concurrente, ventas, evento_id, servicio.reprogramar, ultima)
    _vencer_reintentos(db_concurrente)

    assert cron.ciclo(_sesion(db_concurrente), ventas, lote=20) == 2

    (fecha,) = _fila(db_concurrente, "SELECT fecha FROM eventos WHERE id = :e", e=evento_id)
    assert fecha == ultima
    assert datetime.fromisoformat(ventas.eventos[evento_id]["fecha_inicio"]) == ultima


def test_el_lote_limita_las_operaciones_por_ciclo(db_concurrente, ventas, nuevo_evento):
    for _ in range(3):
        _pendiente(db_concurrente, ventas, nuevo_evento(), servicio.cancelar)
    _vencer_reintentos(db_concurrente)
    assert cron.ciclo(_sesion(db_concurrente), ventas, lote=2) == 2
    assert cron.ciclo(_sesion(db_concurrente), ventas, lote=2) == 1


class VentasLenta(VentasFalsa):
    """Tarda en responder y registra que operaciones estan en vuelo a la vez."""

    def __init__(self):
        super().__init__()
        self.en_vuelo: set[tuple[int, int]] = set()
        self.duplicadas_en_vuelo = 0
        self.envios: dict[tuple[int, int], int] = {}

    def actualizar_evento(self, evento_id, version, **cambios):
        clave = (evento_id, version)
        with self._lock:
            if clave in self.en_vuelo:
                self.duplicadas_en_vuelo += 1
            self.en_vuelo.add(clave)
            self.envios[clave] = self.envios.get(clave, 0) + 1
        time.sleep(0.2)
        try:
            super().actualizar_evento(evento_id, version, **cambios)
        finally:
            with self._lock:
                self.en_vuelo.discard(clave)


def test_dos_ciclos_concurrentes_no_envian_la_misma_operacion(db_concurrente, nuevo_evento):
    ventas = VentasLenta()
    ids = [nuevo_evento() for _ in range(4)]
    for evento_id in ids:
        ventas.eventos[evento_id] = {"version": 0, "fecha_inicio": None, "cancelado": False}
        _pendiente(db_concurrente, ventas, evento_id, servicio.cancelar)
    _vencer_reintentos(db_concurrente)
    ventas.envios.clear()  # cuenta solo los envios del cron

    barrera = threading.Barrier(2)

    def correr():
        barrera.wait()
        cron.ciclo(_sesion(db_concurrente), ventas, lote=20)

    hilos = [threading.Thread(target=correr) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    assert ventas.duplicadas_en_vuelo == 0
    assert sorted(ventas.envios.values()) == [1] * len(ids)  # cada operacion se envio una sola vez
    with db_concurrente.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM operaciones_ventas WHERE estado = 'pendiente'")) == 0


# --- Latido y salud ---------------------------------------------------------------

def test_latido_y_salud(tmp_path):
    latido = str(tmp_path / "latido")
    assert cron.esta_sano(latido, intervalo=5) is False  # sin ningun ciclo todavia
    cron.latir(latido)
    assert cron.esta_sano(latido, intervalo=5) is True
    assert cron.esta_sano(latido, intervalo=5, ahora=time.time() + 16) is False  # mas de 3 intervalos


def test_la_configuracion_del_cron_se_lee_del_entorno(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("CRON_INTERVALO_SEGUNDOS", "2")
    monkeypatch.setenv("CRON_LOTE", "7")
    s = Settings()
    assert (s.cron_intervalo_segundos, s.cron_lote) == (2.0, 7)
