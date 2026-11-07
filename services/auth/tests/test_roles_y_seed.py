"""5.5 Alta de event owners y 5.6 seed idempotente del administrador."""

import pytest
from sqlalchemy import select, text

from app import servicio
from app.models import Usuario

OWNER = {"email": "owner@example.com", "password": "clave-segura-1"}


def _como(rol: str, user_id: int = 1) -> dict:
    return {"X-User-Id": str(user_id), "X-User-Role": rol}


def test_administrador_crea_event_owner(client):
    r = client.post("/auth/event-owners", json=OWNER, headers=_como("administrador"))
    assert r.status_code == 201
    assert r.json()["rol"] == "event_owner"


@pytest.mark.parametrize("rol", ["cliente", "event_owner"])
def test_otros_roles_no_pueden_crear_event_owners(client, db_session, rol):
    r = client.post("/auth/event-owners", json=OWNER, headers=_como(rol))
    assert r.status_code == 403
    assert db_session.scalar(text("SELECT count(*) FROM users")) == 0


def test_sin_identidad_responde_401(client):
    assert client.post("/auth/event-owners", json=OWNER).status_code == 401


def test_seed_es_idempotente_y_no_cambia_la_password(db_session):
    servicio.crear_admin_inicial(db_session, "admin@ticketera.local", "admin-clave-1")
    hash_original = db_session.scalar(select(Usuario.password_hash))
    servicio.crear_admin_inicial(db_session, "admin@ticketera.local", "otra-clave-2")

    admins = db_session.scalars(select(Usuario)).all()
    assert len(admins) == 1
    assert admins[0].rol == "administrador"
    assert admins[0].password_hash == hash_original


def test_seed_sin_credenciales_no_crea_nada(db_session):
    servicio.crear_admin_inicial(db_session, None, None)
    assert db_session.scalar(text("SELECT count(*) FROM users")) == 0


def test_admin_semilla_puede_loguearse(client, db_session):
    servicio.crear_admin_inicial(db_session, "admin@ticketera.local", "admin-clave-1")
    r = client.post("/auth/login", json={"email": "admin@ticketera.local", "password": "admin-clave-1"})
    assert r.status_code == 200
