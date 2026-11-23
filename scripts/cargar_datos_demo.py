"""Carga datos de demo a través del gateway, con el stack levantado.

Uso: python3 scripts/cargar_datos_demo.py

Va por la API y no por SQL para que cada evento publicado llegue también a ventas.
Se puede correr varias veces: los eventos que ya existen (por nombre) se saltean.
Si una corrida falla a mitad de camino, el evento que estaba armando queda incompleto
y las siguientes lo saltean: para empezar de cero, `docker compose down -v`.
"""

import json
import os
import subprocess
import sys
import time as reloj
import urllib.error
import urllib.request
import uuid
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

RAIZ = Path(__file__).resolve().parent.parent


def _leer_env():
    valores = {}
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            linea = linea.strip().removeprefix("export ").strip()
            if "=" in linea and not linea.startswith("#"):
                clave, valor = linea.split("=", 1)
                valores[clave.strip()] = valor.strip().strip("\"'")
    return valores


ENV = _leer_env()


def configuracion(clave, por_defecto=None):
    return os.environ.get(clave) or ENV.get(clave) or por_defecto


GATEWAY = (configuracion("GATEWAY_URL") or f"http://localhost:{configuracion('GATEWAY_PORT', '8000')}").rstrip("/")
OWNER = ("demo-owner@ticketera.local", "demo-owner-123")
CLIENTE = ("demo-cliente@ticketera.local", "demo-cliente-123")
PERFIL_CLIENTE = {
    "nombre": "Cliente", "apellido": "Demo", "dni": "30123456", "fecha_nacimiento": "1990-05-20",
    "telefono": "11 5555-0000", "calle": "Av. Siempre Viva", "numero": "742", "localidad": "La Plata",
    "provincia": "Buenos Aires", "codigo_postal": "1900",
}
ARGENTINA = timezone(timedelta(hours=-3))

RECINTOS = [
    ("Estadio Central", "Av. del Libertador 7000"),
    ("Teatro del Sur", "Av. Corrientes 1500"),
    ("Predio Norte", "Ruta 9 km 30"),
    ("Centro de Convenciones Ribera", "Av. Costanera 2200"),
]

PLATEA_Y_CAMPO = [
    ("Platea", [{"nombre": "Platea A", "tipo": "numerada", "precio": "45000", "filas": ["A", "B", "C"], "asientos_por_fila": 10}]),
    ("Campo", [{"nombre": "Campo general", "tipo": "general", "precio": "25000", "capacidad": 500}]),
]
SALA = [
    ("Platea", [{"nombre": "Platea baja", "tipo": "numerada", "precio": "30000", "filas": ["A", "B", "C", "D"], "asientos_por_fila": 12}]),
    ("Pullman", [{"nombre": "Pullman", "tipo": "numerada", "precio": "18000", "filas": ["E", "F"], "asientos_por_fila": 12}]),
]
SOLO_GENERAL = [
    ("General", [{"nombre": "Acceso general", "tipo": "general", "precio": "60000", "capacidad": 2000}]),
]

# final: borrador | publicado | reprogramado | cancelado. compras: el cliente demo compra al publicarse.
EVENTOS = [
    {"nombre": "Los Pájaros Eléctricos - Gira 2027", "tipo": "recital", "recinto": "Estadio Central", "dias": 20,
     "organizador": "Producciones Faro", "participantes": ["Los Pájaros Eléctricos", "Marea Baja"],
     "descripcion": "Presentación del nuevo disco.", "zonas": PLATEA_Y_CAMPO, "final": "publicado", "compras": True},
    {"nombre": "Hamlet", "tipo": "teatro", "recinto": "Teatro del Sur", "dias": 10,
     "organizador": "Compañía Telón Rojo", "participantes": ["Elenco Telón Rojo"],
     "descripcion": "Versión clásica en dos actos.", "zonas": SALA, "final": "publicado", "compras": True},
    {"nombre": "Final de la Copa Regional", "tipo": "deporte", "recinto": "Estadio Central", "dias": 35,
     "organizador": "Liga Regional", "participantes": ["Club Atlético Norte", "Deportivo Sur"],
     "zonas": PLATEA_Y_CAMPO, "final": "publicado"},
    {"nombre": "Festival Primavera Sonora", "tipo": "festival", "recinto": "Predio Norte", "dias": 90,
     "organizador": "Producciones Faro", "participantes": ["Marea Baja", "Dúo Aurora", "Los Pájaros Eléctricos"],
     "descripcion": "Tres escenarios, dos días.", "zonas": SOLO_GENERAL, "final": "publicado"},
    {"nombre": "Jornada de Ingeniería de Software", "tipo": "conferencia", "recinto": "Centro de Convenciones Ribera",
     "dias": 45, "organizador": "Comunidad Dev Ribera", "participantes": ["Ana Ruiz", "Martín Sosa"],
     "zonas": SOLO_GENERAL, "final": "publicado"},
    {"nombre": "Stand-up de Fin de Año", "tipo": "otro", "recinto": "Teatro del Sur", "dias": 25,
     "organizador": "Risas SRL", "participantes": ["Laura Gil"], "zonas": SALA, "final": "reprogramado"},
    {"nombre": "Dúo Aurora en vivo", "tipo": "recital", "recinto": "Teatro del Sur", "dias": 15,
     "organizador": "Compañía Telón Rojo", "participantes": ["Dúo Aurora"], "zonas": SALA, "final": "cancelado"},
    {"nombre": "Noche de Jazz (en preparación)", "tipo": "recital", "recinto": "Centro de Convenciones Ribera",
     "dias": 60, "organizador": "Comunidad Dev Ribera", "participantes": [], "zonas": SOLO_GENERAL, "final": "borrador"},
    {"nombre": "Obra sin título (borrador)", "tipo": "teatro", "recinto": "Teatro del Sur", "dias": 70,
     "organizador": "Compañía Telón Rojo", "participantes": [], "zonas": [], "final": "borrador"},
]


class ErrorApi(Exception):
    def __init__(self, metodo, ruta, status, cuerpo, retry_after=None):
        super().__init__(f"{metodo} {ruta} -> {status}: {cuerpo}")
        self.status = status
        self.retry_after = retry_after


def pedir(metodo, ruta, cuerpo=None, token=None, headers=None):
    try:
        return _pedir(metodo, ruta, cuerpo, token, headers)
    except ErrorApi as error:
        if error.status != 429:
            raise
        espera = min(int(error.retry_after or 5), 60)
        print(f"… rate limit del gateway: espero {espera} s y reintento")
        reloj.sleep(espera)
        return _pedir(metodo, ruta, cuerpo, token, headers)


def _pedir(metodo, ruta, cuerpo, token, headers):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(f"{GATEWAY}{ruta}", data=datos, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for clave, valor in (headers or {}).items():
        req.add_header(clave, valor)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            texto = resp.read().decode()
            return json.loads(texto) if texto else None
    except urllib.error.HTTPError as error:
        raise ErrorApi(metodo, ruta, error.code, error.read().decode(), error.headers.get("Retry-After")) from None


def credenciales_admin():
    email, password = configuracion("ADMIN_EMAIL"), configuracion("ADMIN_PASSWORD")
    if not email or not password:
        sys.exit("Faltan ADMIN_EMAIL / ADMIN_PASSWORD (en el .env o como variables de entorno).")
    return email, password


def login(email, password):
    return pedir("POST", "/api/auth/login", {"email": email, "password": password})["access_token"]


def asegurar_usuario(ruta, credenciales, token=None, perfil=None):
    try:
        pedir("POST", ruta, {"email": credenciales[0], "password": credenciales[1], **(perfil or {})}, token)
    except ErrorApi as error:
        if error.status != 409:  # 409: ya existe
            raise


CONSULTA_MAILPIT = """
import json, re, sys, urllib.parse, urllib.request
base = "http://mailpit:8025/api/v1/"
leer = lambda ruta: json.load(urllib.request.urlopen(base + ruta, timeout=5))
for mensaje in leer("search?query=" + urllib.parse.quote("to:" + sys.argv[1]))["messages"]:
    link = re.search(r"verificar\\S*[?&]token=([^\\s&]+)", leer("message/" + mensaje["ID"])["Text"])
    if link:
        print(link.group(1))
        break
"""


def token_de_verificacion(email):
    # Mailpit no publica puertos: se lo consulta desde adentro del contenedor de auth.
    # Auth manda el email después de responder el registro, así que puede tardar unos segundos.
    for _ in range(10):
        try:
            resultado = subprocess.run(
                ["docker", "compose", "exec", "-T", "auth", "python", "-c", CONSULTA_MAILPIT, email],
                cwd=RAIZ, capture_output=True, text=True, timeout=30,
            )
        except FileNotFoundError:
            raise RuntimeError("no se encontró el comando docker para leer el email de verificación") from None
        except subprocess.TimeoutExpired:
            raise RuntimeError("mailpit no respondió a tiempo") from None
        if resultado.returncode != 0:
            raise RuntimeError(f"no se pudo consultar mailpit: {resultado.stderr.strip()}")
        if token := resultado.stdout.strip():
            return unquote(token)
        reloj.sleep(1)
    raise RuntimeError(f"no llegó el email de verificación de {email} a mailpit")


def login_verificando(email, password):
    try:
        return login(email, password)
    except ErrorApi as error:
        if error.status != 403:  # 403: email sin verificar
            raise
    pedir("POST", "/api/auth/verificar-email", {"token": token_de_verificacion(email)})
    return login(email, password)


def fecha_en(dias):
    hoy = datetime.now(ARGENTINA).date()
    return datetime.combine(hoy + timedelta(days=dias), time(20, 0), ARGENTINA).isoformat()


def asegurar_recintos(owner):
    existentes = {r["nombre"]: r["id"] for r in pedir("GET", "/api/eventos/recintos")}
    for nombre, direccion in RECINTOS:
        if nombre not in existentes:
            existentes[nombre] = pedir("POST", "/api/eventos/recintos", {"nombre": nombre, "direccion": direccion}, owner)["id"]
    return existentes


def crear_evento(spec, recintos, owner):
    evento = pedir("POST", "/api/eventos", {
        "nombre": spec["nombre"], "fecha": fecha_en(spec["dias"]), "recinto_id": recintos[spec["recinto"]],
        "tipo": spec["tipo"], "organizador": spec["organizador"], "participantes": spec["participantes"],
        "descripcion": spec.get("descripcion", ""),
    }, owner)
    for nombre_sector, zonas in spec["zonas"]:
        sector = pedir("POST", f"/api/eventos/{evento['id']}/sectores", {"nombre": nombre_sector}, owner)
        for zona in zonas:
            pedir("POST", f"/api/eventos/{evento['id']}/sectores/{sector['id']}/zonas", zona, owner)
    return evento["id"]


def comprar(evento_id, cliente):
    disponibilidad = pedir("GET", f"/api/ventas/eventos/{evento_id}/disponibilidad")
    asientos, generales = [], []
    for zona in disponibilidad["zonas"]:
        if zona["tipo"] == "numerada":
            asientos += [a["ticket_id"] for a in zona["asientos"] if a["disponible"]][:2]
        else:
            generales.append({"zona_id": zona["zona_id"], "cantidad": 3})
    reserva = pedir("POST", "/api/ventas/reservas", {"evento_id": evento_id, "asientos": asientos, "generales": generales},
                    cliente, {"Idempotency-Key": str(uuid.uuid4())})
    pedir("POST", f"/api/ventas/reservas/{reserva['id']}/pago", token=cliente)


def main():
    try:
        admin = login(*credenciales_admin())
    except urllib.error.URLError as error:
        sys.exit(f"No se pudo conectar con el gateway en {GATEWAY}. ¿Está levantado el stack? ({error.reason})")
    except ErrorApi as error:
        sys.exit(f"No se pudo entrar como admin: {error}")

    asegurar_usuario("/api/auth/event-owners", OWNER, admin)
    owner = login(*OWNER)
    asegurar_usuario("/api/auth/registro", CLIENTE, perfil=PERFIL_CLIENTE)
    try:
        cliente = login_verificando(*CLIENTE)
    except (ErrorApi, RuntimeError) as error:
        cliente = None
        print(f"! El cliente demo no pudo iniciar sesión; se saltean las compras ({error})")

    recintos = asegurar_recintos(owner)
    ya_cargados = {e["nombre"] for e in pedir("GET", "/api/eventos/mios", token=owner)}

    creados = 0
    for spec in EVENTOS:
        if spec["nombre"] in ya_cargados:
            print(f"= {spec['nombre']}: ya existe")
            continue
        evento_id = crear_evento(spec, recintos, owner)
        if spec["final"] != "borrador":
            pedir("POST", f"/api/eventos/{evento_id}/publicar", token=owner)
            if spec.get("compras") and cliente:
                comprar(evento_id, cliente)
        if spec["final"] == "reprogramado":
            pedir("POST", f"/api/eventos/{evento_id}/reprogramar", {"fecha": fecha_en(spec["dias"] + 14)}, owner)
        elif spec["final"] == "cancelado":
            pedir("POST", f"/api/eventos/{evento_id}/cancelar", token=owner)
        creados += 1
        print(f"+ {spec['nombre']} ({spec['final']})")

    print(f"\n{creados} eventos creados, {len(EVENTOS) - creados} ya existían.")
    print(f"Event owner demo: {OWNER[0]} / {OWNER[1]}")
    if cliente:
        print(f"Cliente demo:     {CLIENTE[0]} / {CLIENTE[1]}")
    else:
        print("Cliente demo:     no disponible (no pudo iniciar sesión, ver el aviso de arriba)")


if __name__ == "__main__":
    main()
