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
| `redis` | Contadores del rate limit | (solo red interna, 6379) |

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
