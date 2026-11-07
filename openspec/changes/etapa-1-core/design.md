# Diseño técnico: Etapa I - Arquitectura base y core

## Context

El repositorio solo contiene la configuración de OpenSpec y el workflow `solo-dev-a-main.yml`; no hay código de aplicación. La motivación y el alcance están en `proposal.md`, y el comportamiento exigido en las specs del change. Este documento explica cómo se construye.

Restricciones que dan forma al diseño: cada microservicio es dueño exclusivo de su base; el gateway debe poder escalar a varias réplicas en la Etapa III sin cambios (stateless); en la Etapa I no hay colas, así que toda comunicación entre servicios es HTTP.

## Goals / Non-Goals

**Goals:**
- Un entorno que se levanta con `docker compose up -d` en una máquina limpia o existente, sin pasos manuales más allá de copiar `.env`.
- Que la regla "un ticket nunca se vende dos veces" se garantice dentro de una sola base, con transacciones locales.
- Que ventas pueda vender aunque eventos esté caído, y que el sistema siga funcionando aunque auth esté caído para usuarios ya logueados.
- Tareas separables por componente, para que tres personas trabajen en paralelo con contratos fijados de antemano.

**Non-Goals:**
- RabbitMQ y comunicación asíncrona (Etapa III).
- nginx como balanceador y réplicas del gateway (Etapa III). En la Etapa I no se usa `X-Forwarded-For`.
- Recomendaciones y cache en Redis (Etapa II).
- Devoluciones y pagos reales (el pago de la Etapa I es simulado y siempre aprueba).
- Un proceso o worker que libere reservas vencidas: el vencimiento se resuelve en las consultas (decisión 11).
- Logout explícito y revocación de tokens de acceso antes de su expiración.

## Decisions

### 1. Topología: una red interna y puertos publicados solo en el borde

Compose crea una única red bridge. Todos los contenedores se resuelven por nombre (`postgres:5432`, `redis:6379`, `auth:8001`, `eventos:8002`, `ventas:8003`). Solo `gateway` (8000) y `frontend` (3000) declaran `ports:`.

```
 host:3000           host:8000
     |                   |
+----v-----+       +-----v-----+
| frontend |       |  gateway  |-----------------+
+----------+       +-----------+                 |
                     |    |    |                 |
            +--------+    |    +--------+        |
            v             v             v        v
         +------+    +---------+    +--------+ +-------+
         | auth |    | eventos |--->| ventas | | redis |
         +------+    +---------+    +--------+ +-------+
            |             |             |
            +-------------+------+------+---- gateway
                                 v
                 +-------------------------------+
                 | postgres                      |
                 | auth_db eventos_db ventas_db  |
                 | gateway_db                    |
                 +-------------------------------+
```

- **Alternativa descartada: dos redes (pública e interna).** El aislamiento respecto del host lo da no publicar puertos, no la cantidad de redes. Una segunda red solo agregaría aislamiento entre contenedores, que en este TP no aporta frente al costo de configuración.

### 2. Un PostgreSQL con una base y un usuario por servicio

`docker/postgres/01-init-databases.sh`, montado en `/docker-entrypoint-initdb.d/`, corre solo cuando el volumen está vacío. Para cada servicio crea el usuario y su base con ese usuario como dueño, y ejecuta `REVOKE CONNECT ON DATABASE <base> FROM PUBLIC` para que solo su dueño pueda conectarse. No crea tablas. Las contraseñas vienen de variables de entorno.

- **Consecuencia aceptada:** una base agregada en una etapa futura no se crea en volúmenes existentes. Hay que correr `docker compose down -v` (perdiendo los datos locales) o crearla a mano. Queda documentado en el README.
- **Alternativa descartada: un PostgreSQL por servicio.** Multiplica el consumo de RAM en las máquinas de desarrollo sin aportar a lo que se evalúa.
- **Alternativa descartada: schemas dentro de una sola base.** El aislamiento de credenciales es más débil y más fácil de romper por error.

### 3. Esquema por Alembic al arrancar cada servicio

Cada servicio con base tiene su `alembic/` y un `entrypoint.sh` que ejecuta `alembic upgrade head` y después `uvicorn`. Como `upgrade head` solo aplica lo pendiente, es seguro en cada arranque. Cuando un compañero agrega una migración, al resto le alcanza con reiniciar el servicio.

Los motores de SQLAlchemy usan `pool_pre_ping=True` para recuperar conexiones después de un reinicio de PostgreSQL. `/health` ejecuta `SELECT 1` contra la base del servicio.

### 4. Orden de arranque

```
postgres (pg_isready)    redis (redis-cli ping)
      |                        |
      +---> auth, eventos, ventas (GET /health)
                   |           |
                   +---> gateway (GET /health: gateway_db + redis)
                              |
                              +---> frontend
```

Se implementa con `healthcheck` en cada contenedor y `depends_on: condition: service_healthy`. Los microservicios no se declaran dependencias entre sí: si eventos tarda, ventas arranca igual y la llamada de publicación falla con 503 hasta que eventos esté arriba. `depends_on` solo actúa en el arranque; la recuperación posterior la dan `restart: unless-stopped` y `pool_pre_ping`.

### 5. Comunicaciones entre componentes

| Origen -> destino | Tipo | Cuándo | Ante falla |
|---|---|---|---|
| frontend -> gateway | Sync (HTTP) | Toda interacción | El frontend muestra el error |
| gateway -> auth | Sync (HTTP, proxy) | Login, registro, refresh, alta de owners | 503 al cliente; el resto del sistema sigue |
| gateway -> eventos | Sync (HTTP, proxy) | Cartelera y gestión de eventos | 503 al cliente |
| gateway -> ventas | Sync (HTTP, proxy) | Disponibilidad, reservas, pagos, cancelaciones, historial | 503 al cliente |
| eventos -> ventas | Sync (HTTP) | Solo al publicar un evento | El evento queda en borrador y se responde 503 |
| gateway -> redis | Sync (TCP) | Cada request (rate limit) | Ver decisión 7 |
| gateway -> postgres | Sync (TCP) | Cada request (bitácora) | Ver decisión 8 |

No hay comunicación asíncrona en la Etapa I. El gateway no llama a auth para validar tokens, y ventas no llama a eventos al reservar, pagar ni cancelar. Las dos llamadas se evitan para que una caída de auth o de eventos no bloquee las compras.

En la Etapa III, la llamada eventos -> ventas pasa a un mensaje `EventoPublicado` por RabbitMQ, y la bitácora pasa a una cola consumida por un worker.

### 6. Pipeline del gateway

El gateway es FastAPI con un middleware único que aplica los pasos en este orden, y un proxy con `httpx.AsyncClient` (timeout 5 s hacia los servicios):

1. `t0 = perf_counter()`; IP del cliente = `request.client.host`.
2. Se eliminan `X-User-Id` y `X-User-Role` de la solicitud entrante.
3. Rate limit (decisión 7). Si excede: 429.
4. Si hay `Authorization: Bearer`, se valida el JWT localmente (HS256, `JWT_SECRET` compartido con auth, verificando `exp`). Token inválido: 401. Rutas protegidas sin token: 401.
5. Se reenvía al servicio según el prefijo (`/api/auth` -> auth, `/api/eventos` -> eventos, `/api/ventas` -> ventas), agregando `X-User-Id` y `X-User-Role` si hay token. Las rutas `/internal/*` de los servicios no tienen prefijo público y no se reenvían.
6. Se registra en la bitácora (decisión 8).
7. Se devuelve la respuesta.

Los servicios confían en `X-User-Id` / `X-User-Role` porque solo son alcanzables desde la red interna, y el gateway garantiza que esos headers nunca vienen del cliente. El gateway configura CORS para el origen del frontend (`CORS_ORIGINS`).

### 7. Rate limit con ventana fija en Redis

Clave `rate_limit:<grupo>:<ip>:<ventana>`, donde `<ventana>` es el minuto actual (epoch // 60). En cada request: `INCR` y, si el valor es 1, `EXPIRE 60`. Si el contador supera el límite del grupo, se responde 429 con `Retry-After = TTL` de la clave.

| Grupo | Rutas | Límite por defecto (por IP y minuto) | Variable |
|---|---|---|---|
| auth | login, registro, refresh | 10 | `RATE_LIMIT_AUTH` |
| compra | reservar, pagar y cancelar | 20 | `RATE_LIMIT_COMPRA` |
| general | todo lo demás | 100 | `RATE_LIMIT_GENERAL` |

- **Fail-open si Redis no responde:** la solicitud continúa y se emite un warning por stdout. Se prioriza la disponibilidad sobre la protección. `/health` del gateway falla, así que el problema queda visible.
- **Alternativa descartada: rate limit en memoria.** Con varias réplicas, cada una tendría su propio contador.
- **Alternativa descartada: ventana deslizante.** Es más precisa, pero más compleja. La ventana fija alcanza para el TP y su `Retry-After` es exacto.

### 8. Bitácora síncrona en `gateway_db`

Tabla `bitacora` (id, timestamp, ip, metodo, ruta, user_id nullable, status, duracion_ms) en `gateway_db`, con migraciones Alembic propias del gateway. El INSERT se hace **antes** de devolver la respuesta, con SQLAlchemy async (asyncpg) y un `statement_timeout` corto (500 ms) para que una base lenta no frene todo el tráfico. Si el INSERT falla, el registro se emite como JSON por stdout y la respuesta se devuelve igual (fail-open).

- **Alternativa descartada: `BackgroundTasks`.** Escribe después de responder; el registro podría perderse sin que nadie se entere, y no respeta el orden "registra y luego retorna".
- **Alternativa descartada: archivos de log en el contenedor.** Rompe el stateless: con réplicas, los logs quedan repartidos y se pierden al recrear el contenedor.
- **Evolución prevista:** si el stress test de la Etapa III muestra contención con ventas, `gateway_db` puede moverse a un PostgreSQL propio cambiando solo `DATABASE_URL`. La alternativa es pasar a cola + worker.

### 9. Tokens: acceso JWT corto y refresh token rotativo

- **Token de acceso:** JWT HS256 con `sub`, `rol`, `exp`. La duración la define `JWT_ACCESS_TTL_MINUTES` (por defecto 120).
- **Refresh token:** valor aleatorio opaco (`secrets.token_urlsafe`) con duración `JWT_REFRESH_TTL_DAYS` (por defecto 7). En `auth_db` se guarda solo su hash SHA-256 en `refresh_tokens(user_id, token_hash UNIQUE, expires_at, used_at)`.
- **Rotación atómica:** `UPDATE refresh_tokens SET used_at = now() WHERE token_hash = :h AND used_at IS NULL AND expires_at > now() RETURNING user_id`. Cero filas: 401. Así, dos refresh simultáneos con el mismo token producen un único par nuevo. El nuevo token de acceso lleva el rol actual del usuario.
- **Contraseñas:** argon2id (`argon2-cffi`). Login con email inexistente o contraseña incorrecta: mismo 401 y mismo mensaje.
- **Administrador inicial:** al arrancar, auth hace `INSERT ... ON CONFLICT (email) DO NOTHING` con `ADMIN_EMAIL` / `ADMIN_PASSWORD`. Así es idempotente y nunca cambia la contraseña de un admin existente.
- **Alternativa descartada: refresh como JWT sin estado.** No se puede invalidar después de usarlo, y la rotación es lo que hace seguro al refresh.

### 10. Propiedad del inventario: eventos define, ventas vende

Eventos guarda la definición (recintos, sectores, zonas, asientos, precios) en `eventos_db`. Al publicar:

1. Eventos valida que el evento esté en borrador y tenga zonas.
2. Llama a `POST ventas:8003/internal/inventario` con `evento_id`, zonas, asientos y precios (timeout 2 s).
3. Ventas inserta todo en una transacción: un ticket por asiento numerado y un ticket por unidad de capacidad en las zonas generales. `inventario_eventos(evento_id PRIMARY KEY)` hace que un reenvío responda 200 sin duplicar.
4. Con la confirmación, eventos marca el evento `publicado`. Si hay timeout o error: 503 y sigue en borrador.

Modelo de `ventas_db`:
- `tickets(id, evento_id, zona_id, tipo_zona, fila, numero, precio, estado, reserva_id, reservado_hasta, orden_id)`. `estado` toma los valores `disponible`, `reservado` o `vendido`. Hay un índice único parcial sobre `(evento_id, zona_id, fila, numero)` para los numerados y un índice `(zona_id, estado)` para buscar disponibles en las zonas generales.
- `reservas(id, user_id, evento_id, hasta, estado, orden_id)`. `estado` toma los valores `activa`, `pagada` o `cancelada`; "vencida" no se guarda, se deduce de `hasta < now()`.
- `ordenes`, `orden_items`, `idempotency_keys(user_id, key, request_hash, reserva_id, UNIQUE(user_id, key))`.

Las zonas generales usan un ticket por entrada, sin fila ni número, en lugar de un contador de cupos. Así el vencimiento de reservas funciona igual para todas las zonas. Una zona de 5000 entradas son 5000 filas, un volumen trivial para PostgreSQL.

- **Alternativa descartada: eventos dueño de la disponibilidad.** La regla de no sobreventa quedaría partida entre dos bases y requeriría una transacción distribuida.
- **Alternativa descartada: ventas consulta a eventos en cada compra.** Acopla la venta a la disponibilidad de eventos y alarga la transacción.

### 11. Reserva con vencimiento perezoso, pago y cancelación

```
             reservar
 disponible ----------> reservado (reservado_hasta = now() + TTL)
     ^                      |        |
     | vence (hasta<now())  |        | pagar antes de vencer
     | o se cancela         |        v
     +----------------------+     vendido (definitivo)
```

**Ticket disponible "efectivo":** `estado = 'disponible' OR (estado = 'reservado' AND reservado_hasta < now())`. Esta condición vive en una sola función del repositorio de ventas, que usan tanto las reservas como la consulta de disponibilidad. Nunca se pregunta solo por `estado = 'disponible'`. El reloj es siempre `now()` de PostgreSQL, nunca la hora del contenedor, para que cualquier réplica decida igual. La duración la define `RESERVA_TTL_MINUTES` (por defecto 5) y el máximo de tickets por reserva `RESERVA_MAX_TICKETS` (por defecto 10, 422 si se supera).

**Reservar** (`POST /reservas`), en una transacción con `SET LOCAL lock_timeout = '2s'`:

1. `INSERT INTO idempotency_keys (user_id, key, request_hash)`. Si choca con el UNIQUE, se espera a la otra transacción. Si la otra confirmó, se devuelve su reserva (o 422 si `request_hash` difiere). Si la otra se revirtió, el INSERT procede.
2. Se crea la fila en `reservas` con `hasta = now() + TTL`.
3. **Numerados:** para cada asiento, en orden de `id` ascendente (evita deadlocks entre reservas cruzadas): `UPDATE tickets SET estado = 'reservado', reserva_id = :r, reservado_hasta = :hasta WHERE id = :id AND evento_id = :e AND <disponible efectivo>`. Si alguno afecta 0 filas: ROLLBACK y 409 indicando los asientos no disponibles.
4. **Generales:** `SELECT id FROM tickets WHERE zona_id = :z AND <disponible efectivo> ORDER BY id LIMIT :n FOR UPDATE SKIP LOCKED`. Si devuelve menos de `:n`: ROLLBACK y 409. Si no, se aplica a esos ids el mismo UPDATE del paso 3.
5. COMMIT. Respuesta 201 con el id de la reserva y `hasta`.

**Pagar** (`POST /reservas/{id}/pago`, pago simulado que siempre aprueba), en una transacción:

1. Si la reserva es de otro usuario: 404. Si ya está `pagada`: se devuelve su orden (idempotente por estado).
2. `UPDATE reservas SET estado = 'pagada' WHERE id = :r AND user_id = :u AND estado = 'activa' AND hasta > now()`. Si son 0 filas: 409 "reserva vencida o cancelada".
3. `UPDATE tickets SET estado = 'vendido', orden_id = :o WHERE reserva_id = :r AND estado = 'reservado' AND reservado_hasta > now()`. Si la cantidad no coincide con la de la reserva: ROLLBACK y 409.
4. Se crean la orden y sus ítems, y COMMIT. Respuesta 201.

**Cancelar** (`DELETE /reservas/{id}`): `UPDATE reservas SET estado = 'cancelada' WHERE ... estado = 'activa'`, y en los tickets `estado = 'disponible', reserva_id = NULL, reservado_hasta = NULL WHERE reserva_id = :r AND estado = 'reservado'`. Si la reserva está pagada: 409.

**Por qué no hay sobreventa ni doble asignación:**
- Dos reservas del mismo asiento: el segundo UPDATE sobre la misma fila espera lo que dura la primera transacción (milisegundos). Después, en READ COMMITTED, re-evalúa el `WHERE` y el ticket ya no es disponible efectivo, así que devuelve 0 filas y responde 409. `lock_timeout` acota esa espera.
- En zonas generales, `SKIP LOCKED` hace que reservas simultáneas tomen tickets distintos en lugar de esperarse. En el peor caso, una reserva recibe 409 aunque otra transacción que tenía filas bloqueadas termine revirtiéndose. Es un falso negativo aceptable: nunca hay sobreventa.
- Pago contra nueva reserva en el instante del vencimiento: ambas son UPDATE sobre las mismas filas de `tickets`, que PostgreSQL serializa. Si gana el pago, la nueva reserva ve `vendido` y recibe 409. Si gana la nueva reserva, el paso 3 del pago no encuentra los tickets y el pago revierte con 409.
- Un rechazo revierte toda la transacción, así que la clave de idempotencia de una reserva rechazada no queda guardada y el reintento se evalúa de nuevo, como pide la spec.

- **Alternativa descartada: un worker o cron que libere reservas vencidas.** En la Etapa I no hay workers. Además deja una ventana en la que el ticket ya venció pero sigue bloqueado hasta la próxima pasada. Con el vencimiento perezoso, el ticket se libera en el instante exacto y sobrevive a reinicios sin lógica extra. Una limpieza periódica podría agregarse en la Etapa III solo para mantener ordenada la tabla.
- **Alternativa descartada: contador de cupos más tabla de reservas para las zonas generales.** Requiere devolver al contador los cupos vencidos y calcular la disponibilidad como contador más vencidas: dos mecanismos distintos y más casos borde.
- **Alternativa descartada: `SELECT ... FOR UPDATE` y después UPDATE en los numerados.** Son dos sentencias para lo que el UPDATE condicional hace en una. Además, sin `NOWAIT` la segunda transacción espera igual, y con `NOWAIT` falla aunque el asiento termine quedando libre.
- **Alternativa descartada: bloqueo optimista con columna de versión.** Agrega reintentos en la aplicación sin ventaja para este caso.

### 12. Estructura del repositorio

```
docker-compose.yml
docker-compose.test.yml      # postgres de test en tmpfs
.env.example
docker/postgres/01-init-databases.sh
gateway/                     # FastAPI, alembic/, tests/, Dockerfile, entrypoint.sh
services/auth/               # idem
services/eventos/            # idem
services/ventas/             # idem
frontend/                    # React 19.3 + Vite, Dockerfile multi-stage
.github/workflows/tests.yml
```

Los servicios backend usan Python 3.12, FastAPI, SQLAlchemy 2.x y psycopg 3; el gateway usa además asyncpg y httpx. El frontend se construye con Vite y se sirve como estático. La URL del gateway llega al frontend por `VITE_API_URL`.

### 13. Tests

- **Base de test separada:** `docker-compose.test.yml` levanta un PostgreSQL en tmpfs. En CI se usa un service container de GitHub Actions. El `conftest.py` común se niega a correr si el nombre de la base no termina en `_test`, para no tocar nunca la base de desarrollo.
- **Rollback por test:** fixture que abre una conexión, inicia una transacción, la entrega a la sesión (y a `TestClient` por override de dependencia) y la revierte al terminar.
- **Concurrencia:** el rollback por test no sirve, porque las transacciones paralelas necesitan conexiones propias y ver los commits de las otras. Fixture separada que crea datos con commits reales, lanza N transacciones en hilos con conexiones independientes y limpia las tablas con TRUNCATE al final. Esos tests se marcan con `@pytest.mark.concurrencia`.
- **Frontend:** Vitest + Testing Library, con MSW interceptando la API del gateway. No se necesita backend.
- **CI:** `.github/workflows/tests.yml` en `pull_request` a cualquier rama. Un job por servicio con PostgreSQL de servicio, un job de frontend y un job que valida `docker compose config`. `solo-dev-a-main.yml` se mantiene sin cambios.

## Risks / Trade-offs

- [Un usuario o bot reserva muchos tickets y los deja vencer, bloqueando la venta durante 5 minutos] -> Lo limitan el rate limit del grupo compra y `RESERVA_MAX_TICKETS`. Un límite de reservas activas por usuario queda como mejora posible.
- [Filas con `estado = 'reservado'` que en realidad ya vencieron] -> Toda lectura usa la condición de disponible efectivo centralizada. Un test verifica que la disponibilidad y la reserva coinciden con una reserva vencida.
- [Volumen de filas en zonas generales grandes] -> Una fila por entrada; con el índice `(zona_id, estado)` la búsqueda de disponibles sigue siendo rápida. El inventario de una zona grande se inserta en bloque.
- [Publicación con timeout pero inventario ya creado en ventas] -> El evento queda en borrador aunque ventas ya tiene su inventario. El reintento es idempotente y lo corrige. Mientras tanto, el frontend no muestra el evento, así que no se puede comprar desde la UI.
- [INSERT de bitácora en cada request bajo carga] -> `statement_timeout` de 500 ms y fail-open. En la Etapa III se mide en el stress test y, si hace falta, se separa la base o se pasa a cola.
- [Fail-open del rate limit si Redis cae] -> Durante la caída no hay protección contra abuso. Queda visible por `/health` y los logs. Se acepta para no tirar todo el sistema por una caída de Redis.
- [Secreto JWT compartido entre auth y gateway] -> Si se filtra, se pueden firmar tokens. Se lee solo de `.env` y nunca se versiona.
- [Token de acceso válido hasta su expiración aunque cambie el rol] -> Como mucho 2 horas por defecto. El refresh siempre emite el rol actual.
- [Bases nuevas en etapas futuras no se crean en volúmenes existentes] -> Documentado en el README; requiere `down -v` o creación manual.
- [PostgreSQL, Redis y el gateway son puntos únicos de falla] -> Aceptado para el TP. En producción se usaría replicación de PostgreSQL, Redis con réplica o Sentinel, y varias réplicas del gateway detrás de nginx redundante.

## Migration Plan

Es el primer despliegue: no hay datos ni versiones previas. Se levanta con `cp .env.example .env` y `docker compose up -d`. El rollback de código es revertir el merge en `dev`. Un rollback de esquema se hace con `alembic downgrade` dentro del servicio correspondiente, y para volver a cero en desarrollo se usa `docker compose down -v`.
