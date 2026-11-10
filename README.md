# Topicos-2 - Ticketera de eventos

Trabajo final de Tópicos II (UNLP). Plataforma de venta de entradas con arquitectura de microservicios.

## Componentes

| Contenedor | Qué hace | Puerto en el host |
|---|---|---|
| `frontend` | SPA React | `3000` |
| `gateway` | Único punto de entrada: JWT, rate limit, bitácora | `8000` |
| `auth` | Usuarios, roles y tokens | (solo red interna, 8001) |
| `eventos` | Eventos, recintos y zonas | (solo red interna, 8002) |
| `ventas` | Inventario, reservas y compras | (solo red interna, 8003) |
| `postgres` | Una base y un usuario por servicio | (solo red interna, 5432) |
| `redis` | Contadores del rate limit y revocación de sesiones | (solo red interna, 6379) |
| `mailpit` | Servidor de email **de desarrollo**: recibe los emails y no los entrega a nadie | (solo red interna, 1025 y 8025) |

Solo `frontend` y `gateway` publican puertos. El resto se accede por nombre dentro de la red de Compose (`postgres:5432`, `auth:8001`, ...).

## Requisitos

- Docker Desktop (o Docker Engine) con Docker Compose v2.

## Primer arranque

```bash
cp .env.example .env
docker compose up -d
```

`.env` tiene las credenciales locales y **no se commitea**. Los valores de `.env.example` sirven para desarrollo.

Con eso:

- Frontend: http://localhost:3000
- Gateway: http://localhost:8000 (estado en http://localhost:8000/health)
- Administrador inicial: el `ADMIN_EMAIL` / `ADMIN_PASSWORD` del `.env`

`docker compose up -d` es idempotente: crea lo que falta (red, volúmenes, imágenes, contenedores) y reutiliza lo que ya existe. Los contenedores arrancan en orden según su estado de salud: `postgres` y `redis`, luego `auth`, `eventos` y `ventas`, luego `gateway`, luego `frontend`. Si un servicio se cae, Docker lo reinicia solo.

## Comandos habituales

| Quiero... | Comando | ¿Y los datos? |
|---|---|---|
| Levantar todo (primera vez o cualquier vez) | `docker compose up -d` | Se mantienen |
| Levantar con mi código nuevo | `docker compose up -d --build` | Se mantienen |
| Pausar todo | `docker compose stop` | Se mantienen |
| Bajar y borrar contenedores | `docker compose down` | Se mantienen (los volúmenes quedan) |
| Empezar de cero | `docker compose down -v` | **Se borran** (bases y Redis) |
| Ver el estado | `docker compose ps` | - |
| Ver los logs de un servicio | `docker compose logs -f ventas` | - |

## Emails (verificación y recuperación de cuenta)

Auth envía emails para verificar la cuenta, restablecer la contraseña y avisar bloqueos. En desarrollo van al contenedor `mailpit`, que **no los entrega a nadie** y, como el resto de los servicios internos, **no publica puertos**: la bandeja no es accesible desde otras máquinas de tu red (los emails tienen links de restablecimiento).

### Cómo controlar los emails

Mailpit es un **buzón de pruebas**: guarda todos los emails que manda el sistema (a cualquier destinatario) y no los entrega a nadie. Hay dos formas de mirarlo. En ambas, el stack tiene que estar levantado (`docker compose up -d`).

**Opción A: en el navegador** (la más cómoda, ideal para la defensa)

1. En una terminal, abrí un túnel temporal que escucha **solo en tu máquina**:

   ```bash
   docker run --rm --network ticketera_net -p 127.0.0.1:8025:8025 alpine/socat TCP-LISTEN:8025,fork TCP:mailpit:8025
   ```

2. Dejá esa terminal abierta y entrá a http://localhost:8025. Vas a ver la bandeja con todos los emails: hacé click en uno para leerlo y abrir su link.
3. Cuando termines, cortá el túnel con **Ctrl+C**. Mientras está abierto no es accesible desde otras máquinas de la red.

**Opción B: por consola** (sin abrir nada)

Listar todos los emails (fecha, destinatario y asunto):

```bash
docker compose exec auth python -c "import urllib.request,json; [print(m['Created'][:19], '|', m['To'][0]['Address'], '|', m['Subject']) for m in json.load(urllib.request.urlopen('http://mailpit:8025/api/v1/messages'))['messages']]"
```

Leer el último email completo (con el link para verificar o restablecer):

```bash
docker compose exec auth python -c "import urllib.request,json; print(json.load(urllib.request.urlopen('http://mailpit:8025/api/v1/message/latest'))['Text'])"
```

Ver solo los emails de un usuario (cambiá el email al final de la URL):

```bash
docker compose exec auth python -c "import urllib.request,json; [print(m['Created'][:19], '|', m['Subject']) for m in json.load(urllib.request.urlopen('http://mailpit:8025/api/v1/search?query=to:ana@example.com'))['messages']]"
```

Vaciar la bandeja:

```bash
docker compose exec auth python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://mailpit:8025/api/v1/messages', method='DELETE')); print('bandeja vacia')"
```

Mailpit no guarda los emails en disco: **al reiniciar Docker o el contenedor, la bandeja queda vacía**. Si "leer el último" da `HTTP Error 404`, es porque no hay ningún email.

Los links de los emails vencen: el de verificación a las 24 horas y el de restablecimiento a los 30 minutos (y solo sirve el último pedido). Si venció, pedí otro desde la app ("Reenviar email de verificación" en el login, o "Olvidé mi contraseña").

**¿Llegó o no llegó?** Si un email no aparece en la bandeja, mirá los logs de auth: los envíos fallidos quedan registrados.

```bash
docker compose logs auth | grep "no se pudo enviar"
```

**Si ya tenías un `.env`** de antes, agregale las variables nuevas de `.env.example`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS`, `EMAIL_FROM` y `FRONTEND_URL` (con los valores de ejemplo funciona con Mailpit).

**Recibir los emails de verdad (opcional).** Mailpit es un buzón de pruebas: los emails existen, pero no llegan a la casilla real del destinatario. Si querés que lleguen (por ejemplo, para la defensa), apuntá auth a un SMTP real **solo en tu `.env`**, sin tocar código ni el compose. Con Gmail:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USER=tu-cuenta@gmail.com
SMTP_PASSWORD=contraseña de aplicación de Google (no tu contraseña normal)
EMAIL_FROM=tu-cuenta@gmail.com
```

La contraseña de aplicación se genera en tu cuenta de Google (Seguridad > Contraseñas de aplicaciones) y requiere la verificación en dos pasos. Después: `docker compose up -d auth`. Para volver a Mailpit, restaurá `SMTP_HOST=mailpit`, `SMTP_PORT=1025` y `SMTP_TLS=false`. Ojo: con SMTP real los emails salen de verdad, así que probá con direcciones propias. Gmail limita los envíos diarios.

**Producción:** no se usa Mailpit. Se cambian las variables `SMTP_*` por las de un proveedor (por ejemplo `SMTP_HOST=smtp.sendgrid.net`, `SMTP_PORT=587`, `SMTP_TLS=true`, usuario y contraseña) y `FRONTEND_URL` por la URL pública. No hay que tocar código.

## Bases de datos y migraciones

- Al crear el volumen de PostgreSQL por primera vez, `docker/postgres/01-init-databases.sh` crea `auth_db`, `eventos_db`, `ventas_db` y `gateway_db`, cada una con su usuario. Cada usuario **solo puede conectarse a su propia base**. El script no crea tablas.
- Las tablas las crean las **migraciones Alembic** de cada servicio, que se aplican solas cada vez que el servicio arranca (`alembic upgrade head`). Nunca se modifica el esquema a mano.
- Para agregar una migración en un servicio:

  ```bash
  docker compose exec ventas alembic revision --autogenerate -m "descripcion"
  ```

> **Importante:** el script de inicialización corre **solo con el volumen vacío**. Si en una etapa futura se agrega una base nueva, en las máquinas que ya tienen el volumen no se va a crear. Para eso hay que correr `docker compose down -v` (se pierden los datos locales) o crear la base y su usuario a mano.

## Tests

Los tests **nunca** usan la base de desarrollo: corren contra un PostgreSQL y un Redis propios, en memoria, definidos en `docker-compose.test.yml` (puertos 5433 y 6380 para no chocar con el entorno de desarrollo). La configuración de tests aborta si la base no termina en `_test`.

### Backend (pytest)

```bash
# 1. Levantar la infraestructura de test (una vez)
docker compose -f docker-compose.test.yml up -d --wait

# 2. Entorno de Python (una vez)
python -m venv .venv
.venv/Scripts/pip install -r services/auth/requirements-dev.txt   # Windows
# .venv/bin/pip install -r services/auth/requirements-dev.txt     # Linux/macOS

# 3. Correr los tests de un servicio desde su carpeta
cd services/auth
../../.venv/Scripts/python -m pytest
```

Cada servicio (`services/auth`, `services/eventos`, `services/ventas`, `gateway`) tiene su propio `requirements-dev.txt` y su carpeta `tests/`.

- Cada test corre dentro de una transacción que se revierte al terminar, así arranca con la base limpia. En el gateway, que es async, las tablas se vacían después de cada test.
- Los tests de concurrencia (`@pytest.mark.concurrencia`) usan conexiones reales en paralelo y limpian las tablas al final.
- Para apuntar a otra base de test: `TEST_DATABASE_URL=...` (tiene que terminar en `_test`).

Para bajar la infraestructura de test (se descarta todo): `docker compose -f docker-compose.test.yml down`.

### Frontend (Vitest)

```bash
cd frontend
npm install
npm test
```

Los tests del frontend simulan la API con MSW, así que no necesitan el backend.

### CI

`.github/workflows/tests.yml` corre todos los tests (backend y frontend) y valida el `docker-compose.yml` en cada pull request. El PR tiene que estar en verde para mergear.

## Flujo de trabajo

- `main`: versión estable. `dev`: integración.
- Todo trabajo sale de `dev` en una rama `feature/<nombre>` o `fix/<nombre>` y vuelve por PR a `dev`.
- Solo `dev` puede abrir PR a `main`.
- Cada PR corre los tests en CI y tiene que pasar antes del merge.
