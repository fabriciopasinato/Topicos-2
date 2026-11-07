# Diseño Técnico: Etapa I - Arquitectura Base y Core

## Context

El proyecto parte de un repositorio sin código de aplicación previo. Se requiere construir una arquitectura de microservicios contenerizada con Docker y Docker Compose, implementando FastAPI en el backend, PostgreSQL para persistencia desacoplada, Redis para rate limit y React 19 en el frontend (ver [proposal.md](proposal.md)).

## Goals / Non-Goals

**Goals:**
- Configurar el orquestador Docker Compose con separación estricta de dos redes (`public_net` e `internal_net`), volúmenes nombrados y políticas de reinicio `restart: unless-stopped` que preserven contenedores y datos existentes.
- Proveer un script SQL en `docker-entrypoint-initdb.d` para inicializar un único contenedor PostgreSQL con 4 bases y usuarios independientes (`auth_db`, `eventos_db`, `ventas_db`, `gateway_db`).
- Implementar el API Gateway stateless con middleware de cronometraje y registro en `gateway_db`, rate limit por IP en Redis y validación de tokens JWT.
- Diseñar la comunicación síncrona HTTP entre `ventas` y `eventos` con control estricto de timeouts.
- Implementar control de concurrencia para evitar sobreventa (pesimista para asientos numerados y atómica para zonas generales) junto con idempotencia mediante `Idempotency-Key`.
- Configurar la estructura de tests con rollback transaccional por prueba en `pytest` y pipeline de CI en GitHub Actions.

**Non-Goals:**
- Colas RabbitMQ o mensajería asíncrona de eventos (diferido a Etapa III).
- Balanceador Nginx frente a réplicas del Gateway (diferido a Etapa III).
- Sistema de recomendación y caching de eventos en Redis (diferido a Etapa II).

## Decisions

### 1. Aislamiento de Redes y Topología Docker Compose
- **Decisión:** Definir dos redes bridge: `public_net` (donde solo exponen puertos al host el `frontend:3000` y el `gateway:8000`) y `internal_net` (privada, donde coexisten `gateway`, `auth`, `eventos`, `ventas`, `postgres` y `redis`).
- **Comportamiento ante reinicios:** Se utilizan volúmenes nombrados (`topicos2_postgres_data` y `topicos2_redis_data`). Si los contenedores ya existen, `docker compose up -d` no recrea ni reinicializa la base de datos, preservando los datos existentes.
- **Alternativas consideradas:**
  - *Red única compartida:* Descartada porque expondría los puertos de base de datos y servicios internos al host o no aislaría el perímetro de seguridad.

### 2. Base de Datos por Microservicio en Único Contenedor
- **Decisión:** Un solo contenedor PostgreSQL que corre un script `01-init-databases.sh` en su arranque inicial creando:
  - `auth_user` / `auth_db`
  - `eventos_user` / `eventos_db`
  - `ventas_user` / `ventas_db`
  - `gateway_user` / `gateway_db`
- **Alternativas consideradas:**
  - *Un contenedor de PostgreSQL por cada microservicio:* Descartado para la Etapa I por consumo innecesario de RAM y complejidad en el entorno de desarrollo local.
  - *Esquemas (schemas) dentro de una misma base:* Descartado porque no garantiza un aislamiento estricto de credenciales y ownership requerido por el trabajo.

### 3. Bitácora de Auditoría en el Gateway
- **Decisión:** El Gateway dispone de su propia base `gateway_db` gestionada con SQLAlchemy y Alembic. Un middleware intercepta la petición, mide el tiempo de respuesta con `time.perf_counter()`, extrae la IP real y el código de respuesta HTTP, y persiste el registro en la base de datos (incluso para respuestas 401 y 429).
- **Alternativas consideradas:**
  - *Guardar logs en archivos del contenedor:* Descartado expresamente por la directiva de alta disponibilidad (el gateway es stateless y múltiples réplicas perderían o fragmentarían los logs).

### 4. Mecanismo de Rate Limiting con Redis
- **Decisión:** Algoritmo de ventana deslizante o contador de tiempo fijo con clave `rate_limit:<ip>:<ventana>` en Redis con TTL de 60 segundos. Si el contador supera 100 req/min (o umbral menor en endpoints `/api/auth/login` y `/api/ventas/comprar`), responde inmediatamente 429 Too Many Requests con `Retry-After: 60`.
- **Alternativas consideradas:**
  - *Rate limit en memoria con dict en Python:* Descartado porque al escalar el gateway a múltiples instancias en Etapa III los contadores no se compartirían.

### 5. Tipo de Comunicación entre Microservicios (Sync vs Async)
- **Decisión:** En esta Etapa I, **todas las comunicaciones entre microservicios son SÍNCRONAS vía HTTP**:
  - `gateway -> auth`: Sync (HTTP POST /login, GET /verify).
  - `gateway -> eventos`: Sync (HTTP GET/POST /eventos).
  - `gateway -> ventas`: Sync (HTTP POST /comprar, GET /tickets).
  - `ventas -> eventos`: Sync (HTTP GET `/internal/eventos/{id}/zonas/{zona_id}`) para verificar estado y precio antes de emitir la compra.
- **Manejo de fallos parciales:** `ventas` utiliza `httpx.AsyncClient` con un timeout máximo de 2.0 segundos. Si `eventos` no responde o falla, `ventas` aborta la transacción y responde HTTP 503 Service Unavailable, evitando bloqueos o estados inconsistentes.

### 6. Prevención de Sobreventa y Concurrencia
- **Decisión:**
  - **Asientos numerados:** Bloqueo pesimista `SELECT ... FOR UPDATE` sobre la fila del asiento o índice único `(evento_id, zona_id, fila, numero_asiento)` con estado en `ventas_db`. La segunda transacción concurrente falla inmediatamente con 409 Conflict.
  - **Zonas generales:** Actualización condicional atómica:
    `UPDATE cupos_zonas SET disponibles = disponibles - :qty WHERE zona_id = :z AND disponibles >= :qty;`
    Si la cantidad de filas afectadas es 0, se arroja 409 Conflict.
  - **Idempotencia:** Tabla `idempotency_records` en `ventas_db` que asocia el `Idempotency-Key` del header con la orden creada. Si la clave ya existe, retorna la orden previa sin duplicar cobros.

## Risks / Trade-offs

- **[Riesgo: Acoplamiento temporal por llamadas síncronas `ventas -> eventos`]** → *Mitigación:* Se configuran timeouts agresivos (2s) y fallback de error explícito (503). En la Etapa III este acoplamiento se migrará a mensajería asíncrona con colas RabbitMQ.
- **[Riesgo: Sobrecarga en `gateway_db` por persistencia síncrona de bitácora]** → *Mitigación:* Se ejecuta la inserción tras despachar la respuesta utilizando `fastapi.BackgroundTasks` o transacción optimizada con pool de conexiones pre-calentado en SQLAlchemy.
- **[Riesgo: Punto único de falla en Gateway / Base de datos]** → *Mitigación:* Aceptado para la entrega del TP; en producción se resolvería con réplicas de PostgreSQL (Streaming Replication) y balanceadores Nginx en alta disponibilidad.

