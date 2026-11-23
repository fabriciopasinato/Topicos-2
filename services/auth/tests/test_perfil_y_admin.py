"""8 Perfil y cambio de contrasenia; 9 administracion de cuentas."""

import time
from types import SimpleNamespace
from typing import get_args

import jwt
import pytest
from sqlalchemy import select, text

from app import revocacion, seguridad
from app.config import get_settings
from app.models import ESTADOS, ROLES, Usuario
from app.schemas import EstadoFiltro, RolFiltro
from tests.conftest import DATOS_REGISTRO, login, token_del_email

NUEVA = "jirafa-violeta-77"
ADMIN = {"X-User-Id": "999", "X-User-Role": "administrador"}


def _como(db_session, rol="cliente") -> dict:
    user_id = db_session.scalar(select(Usuario.id).where(Usuario.email == DATOS_REGISTRO["email"]))
    return {"X-User-Id": str(user_id), "X-User-Role": rol}


# --- 8.1 Perfil --------------------------------------------------------------------

def test_ver_mi_perfil_con_auditoria_y_sin_hash(client, cliente_activo, db_session):
    login(client)
    r = client.get("/auth/perfil", headers=_como(db_session))
    assert r.status_code == 200
    p = r.json()
    assert (p["email"], p["dni"], p["localidad"], p["provincia"]) == ("ana@example.com", "30123456", "La Plata",
                                                                       "Buenos Aires")
    assert p["created_at"] and p["updated_at"] and p["last_login_at"]
    assert "password_hash" not in p and "password" not in p


def test_editar_mi_direccion_actualiza_updated_at(client, cliente_activo, db_session):
    # Para simular una cuenta vieja hay que apagar el trigger un momento
    # (si no, pisa cualquier updated_at que se intente escribir).
    db_session.execute(text("ALTER TABLE users DISABLE TRIGGER trg_users_updated_at"))
    db_session.execute(text("UPDATE users SET updated_at = '2020-01-01'"))
    db_session.execute(text("ALTER TABLE users ENABLE TRIGGER trg_users_updated_at"))

    r = client.patch("/auth/perfil", json={"localidad": "Berisso", "codigo_postal": "1923"}, headers=_como(db_session))
    assert r.status_code == 200
    assert (r.json()["localidad"], r.json()["codigo_postal"]) == ("Berisso", "1923")
    assert not r.json()["updated_at"].startswith("2020")


def test_email_dni_y_rol_no_se_editan(client, cliente_activo, db_session):
    r = client.patch(
        "/auth/perfil",
        json={"email": "otro@x.com", "dni": "11111111", "rol": "administrador", "estado": "activa", "nombre": "Anita"},
        headers=_como(db_session),
    )
    assert r.status_code == 200
    p = r.json()
    assert (p["email"], p["dni"], p["rol"], p["nombre"]) == ("ana@example.com", "30123456", "cliente", "Anita")


def test_editar_con_dato_invalido_responde_422(client, cliente_activo, db_session):
    r = client.patch("/auth/perfil", json={"provincia": "Narnia"}, headers=_como(db_session))
    assert r.status_code == 422


def _perfil(db_session):
    return db_session.execute(text("SELECT localidad, piso_depto FROM users")).one()


@pytest.mark.parametrize("campo", ["nombre", "fecha_nacimiento", "localidad", "provincia", "codigo_postal"])
def test_campo_obligatorio_en_null_responde_422_y_no_cambia_nada(client, cliente_activo, db_session, campo):
    antes = _perfil(db_session)
    r = client.patch("/auth/perfil", json={campo: None, "localidad": "Berisso"} if campo != "localidad"
                     else {campo: None}, headers=_como(db_session))
    assert r.status_code == 422
    assert ["body", campo] in [e["loc"] for e in r.json()["detail"]]
    assert _perfil(db_session) == antes


def test_piso_depto_en_null_lo_vacia(client, cliente_activo, db_session):
    db_session.execute(text("UPDATE users SET piso_depto = '3B'"))
    r = client.patch("/auth/perfil", json={"piso_depto": None}, headers=_como(db_session))
    assert r.status_code == 200 and r.json()["piso_depto"] is None
    assert _perfil(db_session).localidad == "La Plata"


def test_perfil_sin_identidad_responde_401(client):
    assert client.get("/auth/perfil").status_code == 401


# --- 8.2 Cambio de contrasenia -------------------------------------------------------

def _cambiar(client, db_session, actual, nueva):
    return client.post("/auth/perfil/contrasenia", json={"actual": actual, "nueva": nueva},
                       headers=_como(db_session))


def test_cambio_exitoso_revoca_lo_anterior_y_entrega_tokens_nuevos(client, cliente_activo, db_session, redis_test):
    refresh_viejo = login(client).json()["refresh_token"]
    r = _cambiar(client, db_session, DATOS_REGISTRO["password"], NUEVA)
    assert r.status_code == 200
    nuevos = r.json()
    assert client.post("/auth/refresh", json={"refresh_token": refresh_viejo}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": nuevos["refresh_token"]}).status_code == 200
    assert login(client, password=NUEVA).status_code == 200
    user_id = _como(db_session)["X-User-Id"]
    assert redis_test.get(f"revocado:{user_id}") is not None


def test_token_nuevo_no_nace_revocado_aunque_el_commit_cruce_de_segundo(
    client, cliente_activo, db_session, redis_test, monkeypatch
):
    # Simula que entre la firma del token y la publicacion pasaron varios
    # segundos: el reloj que ve revocacion.publicar esta adelantado.
    monkeypatch.setattr(revocacion, "time", SimpleNamespace(time=lambda: time.time() + 5))
    r = _cambiar(client, db_session, DATOS_REGISTRO["password"], NUEVA)
    assert r.status_code == 200

    user_id = _como(db_session)["X-User-Id"]
    marca = int(redis_test.get(f"revocado:{user_id}"))
    iat = jwt.decode(r.json()["access_token"], get_settings().jwt_secret, algorithms=["HS256"])["iat"]
    # Regla del gateway: se rechaza el token si iat < marca.
    assert not iat < marca


def test_contrasenia_actual_incorrecta_responde_422_en_el_campo_actual(client, cliente_activo, db_session, redis_test):
    refresh = login(client).json()["refresh_token"]
    r = _cambiar(client, db_session, "no-es-la-actual", NUEVA)
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "actual"]
    # La contraseña no cambió y la sesión sigue: no hubo revocación.
    assert login(client).status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 200
    assert redis_test.get(f"revocado:{_como(db_session)['X-User-Id']}") is None


def test_nueva_invalida_responde_422(client, cliente_activo, db_session):
    r = _cambiar(client, db_session, DATOS_REGISTRO["password"], "password123")
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "nueva"]
    assert login(client).status_code == 200


# --- 9.1 Listado y detalle -------------------------------------------------------

def _crear_cuentas(db_session, n=30):
    for i in range(n):
        apellido = "Pérez" if i % 10 == 0 else f"Apellido{i}"
        db_session.execute(
            text("INSERT INTO users (email, password_hash, rol, apellido, dni, estado) "
                 "VALUES (:e, 'h', 'cliente', :a, :d, :s)"),
            {"e": f"user{i}@x.com", "a": apellido, "d": f"20{i:06d}", "s": "bloqueada" if i == 5 else "activa"},
        )


def test_busqueda_paginada_sin_tildes(client, db_session):
    _crear_cuentas(db_session)
    r = client.get("/auth/admin/usuarios", params={"q": "perez", "tamanio": 20}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["total"] == 3 and len(r.json()["items"]) == 3
    assert all(u["apellido"] == "Pérez" for u in r.json()["items"])


def test_paginacion_y_total(client, db_session):
    _crear_cuentas(db_session)
    p1 = client.get("/auth/admin/usuarios", params={"tamanio": 20}, headers=ADMIN).json()
    p2 = client.get("/auth/admin/usuarios", params={"tamanio": 20, "pagina": 2}, headers=ADMIN).json()
    assert p1["total"] == 30 and len(p1["items"]) == 20 and len(p2["items"]) == 10
    assert {u["id"] for u in p1["items"]}.isdisjoint(u["id"] for u in p2["items"])


def test_filtros_y_busqueda_por_dni_y_email(client, db_session):
    _crear_cuentas(db_session)
    assert client.get("/auth/admin/usuarios", params={"estado": "bloqueada"}, headers=ADMIN).json()["total"] == 1
    assert client.get("/auth/admin/usuarios", params={"q": "20000007"}, headers=ADMIN).json()["total"] == 1
    assert client.get("/auth/admin/usuarios", params={"q": "USER12@"}, headers=ADMIN).json()["total"] == 1
    assert client.get("/auth/admin/usuarios", params={"rol": "event_owner"}, headers=ADMIN).json()["total"] == 0


@pytest.mark.parametrize("params", [{"rol": "superusuario"}, {"estado": "cualquiera"}])
def test_filtro_con_valor_inexistente_responde_422(client, params):
    assert client.get("/auth/admin/usuarios", params=params, headers=ADMIN).status_code == 422


def test_los_filtros_coinciden_con_roles_y_estados_del_modelo():
    assert set(get_args(RolFiltro)) == set(ROLES)
    assert set(get_args(EstadoFiltro)) == set(ESTADOS)


def _insertar(db_session, email, apellido="X", dni=None):
    db_session.execute(
        text("INSERT INTO users (email, password_hash, rol, apellido, dni, estado) "
             "VALUES (:e, 'h', 'cliente', :a, :d, 'activa')"),
        {"e": email, "a": apellido, "d": dni},
    )


def _buscar(client, q):
    return sorted(u["email"] for u in client.get("/auth/admin/usuarios", params={"q": q}, headers=ADMIN).json()["items"])


def test_busqueda_trata_los_comodines_como_caracteres(client, db_session):
    _insertar(db_session, "a_b@example.com")
    _insertar(db_session, "axb@example.com")
    _insertar(db_session, "cien%@example.com")
    _insertar(db_session, "barra\\@example.com")
    assert _buscar(client, "a_b") == ["a_b@example.com"]
    assert _buscar(client, "%") == ["cien%@example.com"]
    assert _buscar(client, "\\") == ["barra\\@example.com"]
    assert _buscar(client, "_") == ["a_b@example.com"]


def test_busqueda_por_apellido_sigue_ignorando_tildes(client, db_session):
    _insertar(db_session, "p@example.com", apellido="Pérez_Gómez")
    assert _buscar(client, "perez_gomez") == ["p@example.com"]
    assert _buscar(client, "perez%gomez") == []


def test_detalle_sin_hash_y_404(client, cliente_activo, db_session):
    user_id = _como(db_session)["X-User-Id"]
    r = client.get(f"/auth/admin/usuarios/{user_id}", headers=ADMIN)
    assert r.status_code == 200
    d = r.json()
    assert d["estado"] == "activa" and d["intentos_fallidos"] == 0 and "password_hash" not in d
    assert d["created_at"] and d["updated_at"]
    assert client.get("/auth/admin/usuarios/99999", headers=ADMIN).status_code == 404


@pytest.mark.parametrize("rol", ["cliente", "event_owner"])
def test_otros_roles_no_administran(client, rol):
    headers = {"X-User-Id": "1", "X-User-Role": rol}
    assert client.get("/auth/admin/usuarios", headers=headers).status_code == 403
    assert client.get("/auth/admin/usuarios/1", headers=headers).status_code == 403
    assert client.post("/auth/admin/usuarios/1/restablecer-contrasenia", headers=headers).status_code == 403


# --- 9.2 Restablecimiento por el admin -------------------------------------------

def test_admin_restablece_bloquea_revoca_y_envia_email(client, cliente_activo, db_session, enviador, redis_test):
    refresh = login(client).json()["refresh_token"]
    user_id = _como(db_session)["X-User-Id"]
    enviador.enviados.clear()

    r = client.post(f"/auth/admin/usuarios/{user_id}/restablecer-contrasenia", headers=ADMIN)
    assert r.status_code == 202
    assert "password" not in r.text.lower() and DATOS_REGISTRO["password"] not in r.text

    fila = db_session.execute(text("SELECT estado, motivo_bloqueo FROM users WHERE id = :u"), {"u": user_id}).one()
    assert tuple(fila) == ("bloqueada", "restablecimiento_admin")
    assert login(client).json()["codigo"] == "credenciales_invalidas"
    assert client.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401
    assert redis_test.get(f"revocado:{user_id}") is not None

    [email] = enviador.enviados
    assert "administrador" in email.asunto.lower()
    token = token_del_email(email)
    assert client.post("/auth/restablecer-contrasenia", json={"token": token, "contrasenia": NUEVA}).status_code == 200
    assert login(client, password=NUEVA).status_code == 200


def test_admin_restablece_cuenta_inexistente_responde_404(client):
    assert client.post("/auth/admin/usuarios/99999/restablecer-contrasenia", headers=ADMIN).status_code == 404


def test_el_hash_no_se_expone_nunca(client, cliente_activo, db_session):
    user_id = _como(db_session)["X-User-Id"]
    hash_actual = db_session.scalar(select(Usuario.password_hash))
    assert seguridad.verificar_password(hash_actual, DATOS_REGISTRO["password"])
    for r in (client.get("/auth/perfil", headers=_como(db_session)),
              client.get(f"/auth/admin/usuarios/{user_id}", headers=ADMIN),
              client.get("/auth/admin/usuarios", headers=ADMIN)):
        assert hash_actual not in r.text
