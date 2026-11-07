# Propuesta: Etapa I - Arquitectura Base y Core

## Why

Para sentar las bases del trabajo final de Tópicos II (UNLP), es necesario establecer la infraestructura de contenedores, aislamiento de redes, persistencia desacoplada y el núcleo funcional de microservicios de la plataforma ticketera. Esto permite a los tres roles (administrador, event owner y cliente) interactuar de forma segura y concurrente desde la primera entrega, garantizando alta disponibilidad perimetral, idempotencia en la venta y trazabilidad total.

## What Changes

- **Infraestructura y Redes:**
  - Configuración de entorno Docker Compose con dos redes aisladas: `public_net` (para frontend y gateway) y `internal_net` (para microservicios, PostgreSQL y Redis).
  - Configuración de contenedores con `restart: unless-stopped` y volúmenes nombrados para persistencia de datos (manteniendo los contenedores y sus datos entre ejecuciones sin reinicializarlos).
  - Un único contenedor PostgreSQL con bases y usuarios aislados por microservicio (`auth_db`, `eventos_db`, `ventas_db`, `gateway_db`), creados mediante script en `docker-entrypoint-initdb.d`.
  - Contenedor Redis dedicado para contadores de rate limit y sesiones transitorias.
- **API Gateway Stateless:**
  - Punto de entrada unificado y enrutamiento a microservicios internos.
  - Rate limiting por IP configurable mediante Redis (100 req/min por defecto, más estricto para auth y compras) con respuesta 429 y header `Retry-After`.
  - Middleware de bitácora de auditoría que cronometra y persiste en `gateway_db` cada solicitud HTTP entrante y su respuesta.
  - Validación de tokens JWT y propagación de identidad mediante headers internos (`X-User-Id`, `X-User-Role`).
- **Microservicios Core (FastAPI 3.12 + SQLAlchemy 2.x + Alembic):**
  - **Auth Service:** Gestión de usuarios, autenticación y emisión de JWT para roles (`administrador`, `event owner`, `cliente`).
  - **Eventos Service:** Creación y consulta de eventos, recintos, sectores y zonas (numeradas y generales).
  - **Ventas Service:** Reserva y compra de tickets con control de concurrencia (`SELECT FOR UPDATE` para numerados y actualización condicional para generales) y soporte de header `Idempotency-Key`.
  - Endpoints `/health` individuales en cada microservicio para Docker healthchecks.
- **Frontend (React 19.3):**
  - Estructura base de la SPA y mockups/vistas para autenticación, catálogo de eventos y flujo de compra de tickets.
- **Testing y CI:**
  - Tests unitarios y de integración con `pytest` (usando transacciones con rollback por test sobre PostgreSQL) y `vitest` + `msw` para el frontend.
  - Pipeline de GitHub Actions para ejecución automática de tests en cada PR a `dev`.

## Capabilities

### New Capabilities
- `infraestructura/docker-compose`: Orquestación de contenedores, redes `public_net` e `internal_net`, healthchecks, volúmenes y persistencia idempotente.
- `seguridad/gateway-rate-limit-bitacora`: Gateway stateless con rate limit en Redis, bitácora en base de datos y propagación de contexto JWT.
- `autenticacion/usuarios-roles`: Registro, login y control de roles (administrador, event owner, cliente) con contraseñas seguras y JWT.
- `eventos/catalogo-zonas`: Administración y consulta de eventos con sectores, recintos y definición de capacidades (asientos numerados o por zona).
- `ventas/compra-concurrencia`: Flujo de compra y reserva de tickets con garantía de no sobreventa (idempotencia y concurrencia pesimista/atómica).

### Modified Capabilities
*(Ninguna; se trata del primer change del proyecto sobre un repositorio limpio)*

## Impact

- **Código:** Nuevos directorios `gateway/`, `services/auth/`, `services/eventos/`, `services/ventas/` y `frontend/`.
- **APIs:** Endpoints externos en Gateway (`/api/auth/*`, `/api/eventos/*`, `/api/ventas/*`, `/health`) y endpoints internos entre microservicios.
- **Infraestructura:** `docker-compose.yml`, scripts de inicialización SQL de PostgreSQL y `.env.example`.
- **CI/CD:** Archivo de workflow en `.github/workflows/ci.yml`.

