"""Organizadores y participantes sin duplicados: buscar_o_crear."""

import threading

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import servicio
from app.models import Organizador, Participante


# --- Normalizacion (unitarios) --------------------------------------------------

@pytest.mark.parametrize("entrada, limpio, clave", [
    ("Los Piojos", "Los Piojos", "los piojos"),
    ("  Los Piojos  ", "Los Piojos", "los piojos"),        # espacios al principio y al final
    ("Los    Piojos", "Los Piojos", "los piojos"),          # espacios internos colapsados
    ("LOS PIOJOS", "LOS PIOJOS", "los piojos"),            # sin distinguir mayusculas
    ("Los\tPiojos\n", "Los Piojos", "los piojos"),          # tabs y saltos de linea
    ("Fenix", "Fenix", "fenix"),
])
def test_limpiar_y_normalizar(entrada, limpio, clave):
    assert servicio.limpiar_nombre(entrada) == limpio
    assert servicio.normalizar_nombre(entrada) == clave


# --- Integracion ----------------------------------------------------------------

@pytest.mark.parametrize("modelo", [Organizador, Participante])
def test_nombre_nuevo_se_crea(db_session, modelo):
    creado = servicio.buscar_o_crear(db_session, modelo, "Los Piojos")
    assert creado.id is not None and creado.nombre == "Los Piojos" and creado.clave == "los piojos"


@pytest.mark.parametrize("modelo", [Organizador, Participante])
def test_nombre_existente_se_reutiliza(db_session, modelo):
    original = servicio.buscar_o_crear(db_session, modelo, "Los Piojos")
    otro = servicio.buscar_o_crear(db_session, modelo, " los   piojos ")
    assert otro.id == original.id
    assert otro.nombre == "Los Piojos"  # conserva como se escribio la primera vez
    assert db_session.scalar(select(func.count()).select_from(modelo)) == 1


def test_organizador_y_participante_con_el_mismo_nombre_son_distintos(db_session):
    organizador = servicio.buscar_o_crear(db_session, Organizador, "Fenix")
    participante = servicio.buscar_o_crear(db_session, Participante, "Fenix")
    assert isinstance(organizador, Organizador) and isinstance(participante, Participante)


@pytest.mark.parametrize("nombre", ["", "   ", "\t\n"])
def test_nombre_vacio_se_rechaza(db_session, nombre):
    with pytest.raises(servicio.Invalido):
        servicio.buscar_o_crear(db_session, Organizador, nombre)
    assert db_session.scalar(select(func.count()).select_from(Organizador)) == 0


def test_nombre_demasiado_largo_se_rechaza(db_session):
    with pytest.raises(servicio.Invalido):
        servicio.buscar_o_crear(db_session, Participante, "x" * 201)


# --- Concurrencia ---------------------------------------------------------------

@pytest.mark.concurrencia
def test_alta_simultanea_del_mismo_organizador_deja_una_sola_fila(db_concurrente):
    barrera = threading.Barrier(2)
    ids, errores = [], []

    def alta(nombre):
        try:
            with Session(db_concurrente) as session:
                barrera.wait()
                ids.append(servicio.buscar_o_crear(session, Organizador, nombre).id)
                session.commit()
        except Exception as error:  # noqa: BLE001
            errores.append(error)

    hilos = [threading.Thread(target=alta, args=(n,)) for n in ("Fenix", "  FENIX ")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    assert not errores
    assert len(ids) == 2 and ids[0] == ids[1]
    with Session(db_concurrente) as session:
        assert session.scalar(select(func.count()).select_from(Organizador)) == 1
