# Propuesta: Etapa I - Arquitectura base y core

## Why

El repositorio no tiene código de aplicación: hace falta levantar la arquitectura de microservicios completa (contenedores, red, bases por servicio, gateway) y el núcleo funcional de la ticketera (usuarios y roles, eventos con zonas, compra de tickets sin sobreventa) para la primera entrega. Todo en un único change para la Etapa I, con tareas agrupadas por componente para que el equipo de tres personas pueda repartirlas y trabajar en paralelo.

## What Changes

- **Infraestructura Docker Compose**
  - Una sola red interna de Compose. Solo `frontend` y `gateway` publican puertos al host; `postgres`, `redis` y los microservicios no publican puertos.
  - Un contenedor PostgreSQL con 4 bases y 4 usuarios (`auth_db`, `eventos_db`, `ventas_db`, `gateway_db`). Cada usuario solo puede conectarse a su propia base.
  - Script de inicialización único que corre solo con el volumen vacío y crea únicamente bases, usuarios y permisos. Todo el esquema lo maneja Alembic, que cada servicio aplica al arrancar.
  - Orden de arranque por healthchecks: `postgres` y `redis` -> `auth`, `eventos`, `ventas` -> `gateway` -> `frontend`. Los microservicios no dependen entre sí.
  - `docker compose up -d` crea lo que falta y reutiliza lo existente (volúmenes nombrados, `restart: unless-stopped`).
  - `.env.example` versionado, `.env` ignorado, README con el arranque y los comandos habituales.
- **Gateway** (servicio de borde sin lógica de negocio)
  - Pipeline por request: timer -> descarte de headers de identidad enviados por el cliente -> rate limit en Redis -> validación local del JWT -> reenvío con `X-User-Id` / `X-User-Role` -> bitácora -> respuesta.
  - Rate limit por IP con tres grupos configurables (auth, compra, general con 100 req/min por defecto), 429 con `Retry-After` igual al tiempo restante de la ventana.
  - Bitácora persistida en `gateway_db` antes de responder, incluyendo 401 y 429.
- **Auth**
  - Registro público que siempre crea usuarios `cliente`. Solo un administrador crea `event owner`. Seed idempotente del administrador inicial.
  - Login con contraseña hasheada y JWT de acceso con expiración configurable (2 horas por defecto), más un refresh token rotativo para renovarlo.
- **Eventos** (define qué se vende)
  - Eventos, recintos, sectores y zonas numeradas o generales. Estados `borrador` -> `publicado`; el owner solo gestiona sus eventos.
  - Al publicar, envía el inventario a ventas por HTTP sync. Si ventas no responde, el evento queda en borrador.
- **Ventas** (única fuente de verdad de qué está vendido)
  - Inventario propio: un ticket por entrada, tanto en zonas numeradas como generales, con copia del precio. Reservar, pagar y cancelar no consultan a eventos.
  - Compra en dos pasos. La reserva bloquea los tickets por 5 minutos (configurable) o hasta el pago, lo que ocurra primero; si vence o se cancela, los tickets vuelven a estar disponibles. El pago es simulado.
  - Sin sobreventa (actualizaciones condicionales atómicas) y con creación de reservas idempotente mediante `Idempotency-Key`.
- **Frontend**: SPA React 19.3 con vistas de login/registro, catálogo y compra (numerados y por zona), testeada con MSW.
- **Testing y CI**: base de test separada, fixtures de rollback y de concurrencia, workflow que corre pytest y Vitest en cada PR.

## Capabilities

### New Capabilities
- `infraestructura/docker-compose`: orquestación de contenedores, red interna, bases y usuarios aislados por servicio, orden de arranque, healthchecks y persistencia entre ejecuciones.
- `seguridad/gateway-rate-limit-bitacora`: punto de entrada único y stateless con validación JWT, propagación de identidad, rate limit por IP y bitácora de todas las solicitudes.
- `autenticacion/usuarios-roles`: registro, login, renovación de tokens, roles (administrador, event owner, cliente) y administrador inicial.
- `eventos/catalogo-zonas`: gestión y consulta de eventos con recintos, sectores y zonas, ciclo borrador/publicado y entrega del inventario a ventas.
- `ventas/compra-concurrencia`: inventario de tickets, reserva con vencimiento, pago y cancelación, sin sobreventa bajo concurrencia y con reservas idempotentes.

### Modified Capabilities
_(Ninguna: es el primer change del proyecto y no hay specs existentes.)_

## Impact

- **Código nuevo**: `docker-compose.yml`, `docker/postgres/`, `gateway/`, `services/auth/`, `services/eventos/`, `services/ventas/`, `frontend/`, `.env.example`, `README.md`.
- **APIs externas (vía gateway)**: `/api/auth/*`, `/api/eventos/*`, `/api/ventas/*`, `/health`.
- **APIs internas**: `POST /internal/inventario` en ventas (llamado por eventos). Ningún endpoint interno es accesible desde el host.
- **Dependencias**: PostgreSQL, Redis, FastAPI, SQLAlchemy 2.x, Alembic, httpx, React 19.3, Vite, Vitest, MSW.
- **CI**: nuevo workflow de tests en `.github/workflows/`; se mantiene `solo-dev-a-main.yml`.
