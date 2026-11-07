# Tasks: Etapa I - Arquitectura Base y Core

## 1. Infraestructura Base y Redes Docker

- [ ] 1.1 Crear el archivo `.env.example` con las variables de configuración de puertos, credenciales de PostgreSQL (`auth_db`, `eventos_db`, `ventas_db`, `gateway_db`), Redis y JWT secret, verificando que contenga valores por defecto funcionales para desarrollo.
- [ ] 1.2 Crear el script `init-databases.sh` en `docker/postgres/` para la creación automática e idempotente de las 4 bases de datos y usuarios correspondientes en PostgreSQL, verificando permisos y ownership.
- [ ] 1.3 Crear el archivo `docker-compose.yml` definiendo los servicios `postgres`, `redis`, `gateway`, `auth`, `eventos`, `ventas` y `frontend`, las dos redes (`public_net` e `internal_net`), volúmenes nombrados persistentes y políticas `restart: unless-stopped`, verificando que la sintaxis de compose sea válida mediante `docker compose config`.
- [ ] 1.4 Crear los `Dockerfile` independientes para cada componente (`gateway/Dockerfile`, `services/auth/Dockerfile`, `services/eventos/Dockerfile`, `services/ventas/Dockerfile` y `frontend/Dockerfile`) con Python 3.12 y Node para React, verificando que expongan sus endpoints de salud.

## 2. API Gateway: Autenticación, Rate Limit y Bitácora

- [ ] 2.1 Configurar el proyecto FastAPI en `gateway/` con SQLAlchemy 2.x, Alembic y el modelo de datos para la tabla `bitacora_peticiones` en `gateway_db`, generando la migración inicial de Alembic y verificando su aplicación.
- [ ] 2.2 Implementar el cliente Redis y el middleware de Rate Limiting por IP (100 req/min general, con límites restrictivos configurables para rutas de login y compras), verificando con tests unitarios que responde 429 con header `Retry-After`.
- [ ] 2.3 Implementar el middleware de Bitácora que cronometra cada petición entrante y persiste el registro en `gateway_db`, verificando con tests de integración que todas las respuestas (incluyendo 200, 401 y 429) queden grabadas en la base.
- [ ] 2.4 Implementar la validación stateless de tokens JWT en el Gateway y la propagación de identidad mediante inyección de headers internos `X-User-Id` y `X-User-Role`, verificando con tests unitarios y de integración.

## 3. Microservicio Auth: Usuarios y Roles

- [ ] 3.1 Configurar la estructura de `services/auth/` con FastAPI, SQLAlchemy 2.x y Alembic, creando los modelos de `User` y `Role` (`administrador`, `event owner`, `cliente`) y generando la migración inicial de Alembic.
- [ ] 3.2 Implementar los endpoints de registro y login (`/login`) con hashing seguro de contraseñas y emisión de JWT, verificando con tests unitarios de negocio y tests de integración con rollback en `conftest.py`.
- [ ] 3.3 Implementar el endpoint `/health` y verificar su respuesta 200 OK para el healthcheck de Docker.

## 4. Microservicio Eventos: Catálogo y Zonas

- [ ] 4.1 Configurar la estructura de `services/eventos/` con FastAPI, SQLAlchemy 2.x y Alembic, creando los modelos para eventos, recintos, sectores y zonas (numeradas y generales), y generando la migración inicial de Alembic.
- [ ] 4.2 Implementar los endpoints CRUD de gestión de eventos restringidos al rol `event owner` y endpoints públicos de consulta de cartelera, verificando con tests unitarios y de integración.
- [ ] 4.3 Implementar el endpoint interno `/internal/eventos/{id}/zonas/{zona_id}` para permitir la consulta síncrona de disponibilidad desde el servicio de ventas, verificando con tests de integración.
- [ ] 4.4 Implementar el endpoint `/health` y verificar su respuesta 200 OK para el healthcheck de Docker.

## 5. Microservicio Ventas: Compras, Concurrencia e Idempotencia

- [ ] 5.1 Configurar la estructura de `services/ventas/` con FastAPI, SQLAlchemy 2.x y Alembic, creando los modelos para órdenes de compra, tickets y registro de claves de idempotencia, y generando la migración inicial de Alembic.
- [ ] 5.2 Implementar el cliente HTTP síncrono interno con `httpx` (timeout de 2s) hacia el servicio de eventos para validar disponibilidad y precio de localidades antes de vender, verificando el manejo de fallos y respuestas 503 con tests unitarios mockeados.
- [ ] 5.3 Implementar la lógica de reserva y compra para asientos numerados utilizando bloqueo pesimista o restricciones de unicidad, verificando con un test de concurrencia que dos compras simultáneas para el mismo asiento terminen en un 201 Created y un 409 Conflict.
- [ ] 5.4 Implementar la lógica de compra para zonas generales con decremento atómico de cupo y soporte de header `Idempotency-Key`, verificando con tests unitarios y de integración que los reintentos devuelvan la misma orden sin duplicar tickets.
- [ ] 5.5 Implementar el endpoint `/health` y verificar su respuesta 200 OK para el healthcheck de Docker.

## 6. Frontend y Mockups Core

- [ ] 6.1 Inicializar la aplicación React 19.3 en `frontend/` con Vite, Tailwind/CSS y configuración de `vitest` + `Testing Library` + `MSW`.
- [ ] 6.2 Implementar las vistas y componentes para login/registro de usuarios, catálogo de eventos y selección/compra de tickets (numerados y por zona), verificando con tests de componentes en Vitest usando MSW.

## 7. Integración Continua (CI)

- [ ] 7.1 Crear el workflow `.github/workflows/ci.yml` configurado para correr en cada PR contra `dev`, ejecutando los linter/formateadores, los tests de backend con pytest (usando un servicio Postgres efímero de test) y los tests de frontend con vitest, verificando que el workflow sea sintácticamente válido.

