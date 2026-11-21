"""Matriz de acciones permitidas por estado (unitario, sin base).

La tabla esperada se escribe aca a mano, a partir de lo acordado en la spec,
en lugar de importarla: si alguien cambia una celda del codigo por error, este
test lo detecta.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.servicio import Accion, Conflicto, exigir_permitido

AHORA = datetime(2030, 1, 1, tzinfo=UTC)
FUTURO = AHORA + timedelta(days=30)
PASADO = AHORA - timedelta(hours=1)

#                     editar recinto zonas publicar reprogramar cancelar borrar
ESPERADO = {
    "borrador":   dict(EDITAR=1, CAMBIAR_RECINTO=1, MODIFICAR_ZONAS=1, PUBLICAR=1, REPROGRAMAR=1, CANCELAR=1, BORRAR=1),
    "publicado":  dict(EDITAR=1, CAMBIAR_RECINTO=0, MODIFICAR_ZONAS=0, PUBLICAR=0, REPROGRAMAR=1, CANCELAR=1, BORRAR=0),
    "finalizado": dict(EDITAR=0, CAMBIAR_RECINTO=0, MODIFICAR_ZONAS=0, PUBLICAR=0, REPROGRAMAR=0, CANCELAR=0, BORRAR=0),
    "cancelado":  dict(EDITAR=0, CAMBIAR_RECINTO=0, MODIFICAR_ZONAS=0, PUBLICAR=0, REPROGRAMAR=0, CANCELAR=0, BORRAR=0),
}

# Como se llega a cada estado informado: (estado guardado, fecha de inicio).
EVENTOS = {
    "borrador": ("borrador", FUTURO),
    "publicado": ("publicado", FUTURO),
    "finalizado": ("publicado", PASADO),  # calculado: publicado cuya fecha ya llego
    "cancelado": ("cancelado", FUTURO),
}


def test_la_tabla_esperada_cubre_todas_las_acciones():
    assert all(set(fila) == {a.name for a in Accion} for fila in ESPERADO.values())


@pytest.mark.parametrize("estado, accion, permitido", [
    (estado, accion, bool(permitidos[accion])) for estado, permitidos in ESPERADO.items() for accion in permitidos
])
def test_matriz(estado, accion, permitido):
    guardado, fecha = EVENTOS[estado]
    evento = SimpleNamespace(estado=guardado, fecha=fecha)
    if permitido:
        exigir_permitido(evento, Accion[accion], AHORA)
    else:
        with pytest.raises(Conflicto):
            exigir_permitido(evento, Accion[accion], AHORA)


def test_un_borrador_con_fecha_pasada_sigue_siendo_borrador():
    exigir_permitido(SimpleNamespace(estado="borrador", fecha=PASADO), Accion.BORRAR, AHORA)
