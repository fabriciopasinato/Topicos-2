# Design

## Context

La motivación está en `proposal.md` (Why) y los comportamientos esperados en las specs del change. Este documento explica cómo construirlo sobre lo que ya existe:

- **eventos** tiene una sola migración (`0001_catalogo`) con `recintos`, `eventos`, `sectores`, `zonas` y `asientos`. El estado es un texto con un `CheckConstraint` (`borrador`, `publicado`). La lógica vive en `app/servicio.py`, que recibe una `Session` y no conoce HTTP, y la única llamada a otro servicio está en `app/cliente_ventas.py` (`POST ventas:8003/internal/inventario`, timeout de 2 s).
- La publicación ya resuelve un caso de consistencia entre servicios: lock de la fila del evento, llamada sync a ventas, y el cambio a `publicado` solo si ventas confirma. El reintento lo hace el owner a mano, y ventas es idempotente por `evento_id`.
- **ventas** registra los inventarios recibidos en `inventario_eventos (evento_id, created_at)`, que hoy funciona solo como marca de idempotencia. `reservar` y `pagar` resuelven todo con datos propios y usan siempre `now()` de PostgreSQL como reloj.
- El gateway ya trata como públicas todas las rutas `GET /api/eventos*` y no reenvía `/internal/*`.

## Goals / Non-Goals

**Goals:**

- Que la reprogramación y la cancelación de un evento publicado lleguen a ventas **siempre**, aunque ventas esté caído o eventos se detenga en medio de la operación.
- Que ninguna entrada se venda después de una cancelación confirmada, ni después de la fecha de inicio, sin agregar llamadas de ventas a eventos.
- Que la búsqueda y las recomendaciones de las etapas siguientes encuentren el modelo listo: tipo, organizador y participantes indexables.

**Non-Goals:**

- Migrar la publicación al outbox. Sigue siendo sync con reintento manual, como hoy.
- Notificar a los compradores o devolver dinero.
- Reemplazar HTTP por una cola. El outbox se diseña para que en la Etapa III el envío pase a RabbitMQ sin cambiar el resto.

## Decisions

### 1. Comunicación entre servicios

| Origen -> destino | Operación | Tipo | Garantía |
|---|---|---|---|
| eventos -> ventas | Publicar (inventario + fecha de inicio) | Sync HTTP `POST /internal/inventario` | Igual que hoy: 503 y reintento manual del owner. Idempotente por evento. |
| eventos -> ventas | Reprogramar / cancelar un evento publicado | Sync HTTP `PUT /internal/eventos/{id}`, con outbox y reintento periódico | Consistencia eventual. Al menos una entrega; idempotente y tolerante al desorden gracias a la versión. |
| ventas -> eventos | Ninguna | - | Ventas nunca consulta a eventos. |

No hay comunicación asíncrona por cola en este change.

### 2. Organizadores y participantes como entidades mínimas

Las tablas `organizadores (id, nombre, clave)` y `participantes (id, nombre, clave)` tienen un índice único sobre `clave`, que es el nombre normalizado (minúsculas, sin espacios al principio ni al final, y con los espacios internos colapsados). `nombre` guarda cómo se escribió la primera vez. La relación con eventos es `eventos.organizador_id` (N:1) y la tabla `evento_participantes (evento_id, participante_id)` (N:N, con clave primaria compuesta y borrado en cascada desde el evento).

Una sola función `buscar_o_crear(session, Modelo, nombre)` resuelve las dos entidades. Hace `INSERT ... ON CONFLICT (clave) DO NOTHING RETURNING id` y, si no devuelve nada, `SELECT` por clave. Así dos altas simultáneas del mismo nombre terminan en una sola fila, sin capturar errores de integridad.

- *Alternativa descartada: una sola tabla `entidades` con columna `tipo`.* La base no podría impedir que `organizador_id` apunte a un participante, y los atributos propios de cada uno (CUIT, disciplina) terminarían como columnas vacías en la mitad de las filas.
- *Alternativa descartada: texto libre en el evento.* Si más adelante hacen falta más datos, habría que deduplicar todos los nombres ya cargados.

### 3. Tipo como enum de código con check en la base

Un `enum.StrEnum` en `app/models.py` con los seis valores, validado por Pydantic en la API y por un `CheckConstraint` en la tabla, con el mismo patrón que `estado`. Pasarlo a una tabla más adelante es una migración.

### 4. Estado guardado y estado calculado

En la base se guardan `borrador`, `publicado` y `cancelado` (el check se amplía). `finalizado` se calcula al responder: `estado = publicado AND fecha <= now()`. El reloj es el de PostgreSQL, igual que en ventas, para que los dos servicios coincidan en cuándo empezó un evento. La cartelera filtra en SQL con `fecha > now()`.

Se agrega `publicado_at` (nullable), que se completa al publicar. Sirve para decidir la visibilidad de un evento cancelado: es público solo si `publicado_at IS NOT NULL`.

- *Alternativa descartada: guardar `finalizado` y actualizarlo con un job.* Puede quedar desfasado entre corridas y no aporta nada que el cálculo no dé.

### 5. Outbox de operaciones hacia ventas

Hay una tabla nueva `operaciones_ventas`:

| Columna | Uso |
|---|---|
| `id` | Orden de procesamiento |
| `evento_id` | FK a `eventos` |
| `tipo` | `reprogramar` o `cancelar` |
| `version` | Versión asignada a este cambio |
| `fecha` | Nueva fecha (solo en `reprogramar`) |
| `estado` | `pendiente` o `confirmada` |
| `intentos`, `ultimo_error`, `proximo_intento_at` | Reintentos con espera creciente |
| `created_at`, `confirmada_at` | Auditoría |

Hay un índice parcial sobre `(proximo_intento_at) WHERE estado = 'pendiente'` para que el cron encuentre rápido lo pendiente.

En `eventos` se agregan dos contadores:
- `version`: la última versión **asignada**.
- `version_aplicada`: la última versión **aplicada** en eventos.

**Flujo** (reprogramar o cancelar un evento publicado):

```
 TX1  SELECT evento FOR UPDATE
      validar (estado, fecha futura, sin cancelacion pendiente)
      evento.version += 1
      INSERT operaciones_ventas (pendiente, version)
      COMMIT                                   <- la intencion queda guardada

 HTTP PUT ventas /internal/eventos/{id} {version, fecha | cancelado}   (sin locks tomados)
      ok    -> TX2: aplicar(op) ; op.estado = confirmada  -> 200
      falla -> op queda pendiente                         -> 202
```

`aplicar(op)` es la misma función para la API y para el cron. Toma el lock del evento y aplica solo si `op.version > evento.version_aplicada`, y nunca sobre un evento ya `cancelado`. Después actualiza `version_aplicada`. Esto hace que confirmar dos veces, o en desorden, no tenga efecto.

En borrador no hay outbox: la reprogramación y la cancelación se aplican en una sola transacción y responden 200.

**Bloqueo por cancelación pendiente**: dentro de TX1, si existe una operación `cancelar` pendiente para el evento, la reprogramación y el `PATCH` responden 409. El lock del evento serializa ese chequeo con la inserción de la cancelación, así que dos pedidos simultáneos no pueden saltearse la regla.

**Lo que ve el owner**: el detalle del evento (solo para el owner y los administradores) incluye `operaciones_pendientes: [{tipo, fecha?, created_at}]`.

- *Alternativa descartada: aplicar en eventos de inmediato y sincronizar después.* Si se adelanta la fecha, ventas podría vender después del inicio real mientras el cambio está pendiente.
- *Alternativa descartada: una `Idempotency-Key` por operación.* Resuelve los duplicados pero no el desorden. La versión resuelve los dos problemas y no necesita una tabla de claves en ventas.

### 6. Proceso `eventos-cron`

Es un módulo `app/cron.py` con un bucle simple: cada `CRON_INTERVALO_SEGUNDOS` (5 s por defecto) toma hasta `CRON_LOTE` operaciones con `SELECT ... WHERE estado = 'pendiente' AND proximo_intento_at <= now() ORDER BY id FOR UPDATE SKIP LOCKED`. Para cada una llama a ventas y, si responde bien, ejecuta `aplicar` y la marca como confirmada. Si falla, incrementa `intentos` y posterga `proximo_intento_at` con espera exponencial, con un máximo de 60 s. Corre en el mismo contenedor de imagen que eventos, con otro comando (`python -m app.cron`).

- `SKIP LOCKED` permite correr más de una instancia sin que dos envíen la misma operación a la vez. Si el envío inmediato de la API coincide con el del cron, ventas lo absorbe por la versión.
- **Healthcheck**: al terminar cada ciclo el proceso actualiza un archivo de latido (`/tmp/cron-heartbeat`). El healthcheck falla si el archivo tiene más de 3 intervalos de antigüedad. Así un bucle colgado figura como unhealthy, y con `restart: unless-stopped` una caída se recupera sola.
- `depends_on: eventos (service_healthy)`, porque eventos aplica las migraciones al arrancar. No depende de ventas.
- *Alternativa descartada: una tarea de fondo dentro de la API.* Correría una vez por réplica y moriría con cada reinicio de la API.
- *Alternativa descartada: un cron central con módulos por servicio.* Necesitaría las credenciales de todas las bases y rompería el aislamiento de datos.
- *Alternativa descartada: APScheduler o el `cron` del sistema.* Un bucle con `sleep` alcanza, sin dependencias nuevas.

### 7. Cambios en ventas

- **Migración `0002`**: `inventario_eventos` suma `fecha_inicio TIMESTAMPTZ NULL`, `cancelado BOOLEAN NOT NULL DEFAULT false` y `version INTEGER NOT NULL DEFAULT 0`.
- `POST /internal/inventario` acepta `fecha_inicio`, opcional para no romper envíos anteriores.
- **`PUT /internal/eventos/{evento_id}`** con el cuerpo `{version, fecha_inicio?, cancelado?}`. Ejecuta un único UPDATE condicional:
  ```sql
  UPDATE inventario_eventos
     SET version = :v,
         cancelado = cancelado OR :cancelar,
         fecha_inicio = CASE WHEN cancelado THEN fecha_inicio ELSE COALESCE(:fecha, fecha_inicio) END
   WHERE evento_id = :e AND version < :v
  ```
  Si no actualizó ninguna fila y el evento existe, responde 200 (versión vieja o repetida). Si el evento no existe, responde 404.
- **Cierre de la venta**: `reservar` y `pagar` leen `inventario_eventos` con `FOR SHARE` al principio de su transacción y responden 409 si `cancelado` es verdadero o `fecha_inicio <= now()`. Como el UPDATE de la cancelación toma un lock exclusivo sobre esa misma fila, una reserva y una cancelación simultáneas quedan serializadas. La reserva ve el evento cancelado, o termina antes y su pago posterior lo ve. Si no hay fila de inventario, se mantiene el comportamiento actual.

### 8. API de eventos

| Método y ruta | Cambio |
|---|---|
| `POST /eventos` | Suma `tipo`, `organizador`, `participantes[]` y `descripcion`. |
| `PATCH /eventos/{id}` | Edita los datos descriptivos, y el `recinto_id` solo en borrador. Si llega `fecha`, responde 422 con un mensaje que indica usar la reprogramación. |
| `POST /eventos/{id}/reprogramar` | `{fecha}`. Responde 200 si se aplicó, o 202 con el evento y la operación pendiente. |
| `POST /eventos/{id}/cancelar` | Responde 200 si se aplicó, o 202 si quedó pendiente. Si ya está cancelado, 200 sin hacer nada. |
| `DELETE /eventos/{id}` | Responde 204, solo en borrador. |
| `GET /eventos?tipo=&desde=&hasta=` | Filtros de la cartelera. |
| `POST /eventos/{id}/publicar` | Envía `fecha_inicio`, registra `publicado_at`, y responde 422 si la fecha ya pasó. |

Las respuestas de detalle y resumen agregan `tipo`, `descripcion`, `organizador {id, nombre}`, `participantes [{id, nombre}]` y el `estado` calculado.

### 9. Frontend del event owner

Son rutas bajo `/owner`, visibles para `event_owner` y `administrador`: "Mis eventos" (`GET /eventos/mios`), crear y editar un evento, armar sectores y zonas, publicar, reprogramar, cancelar y borrar, y ver las operaciones pendientes. Reutiliza el cliente de API existente y la protección de rutas por rol (`SoloRol`) del change de auth. Si ese change todavía no está en `dev` al llegar a esta parte, se trae `dev` a la rama antes de empezar. Los tests usan MSW, como el resto del frontend.

## Risks / Trade-offs

- **[El owner recibe 202 y no entiende qué pasó]** -> El detalle muestra la operación pendiente, y el frontend lo explica ("la cancelación se completará cuando ventas esté disponible").
- **[El cron se cae o se cuelga y lo pendiente no avanza]** -> `restart: unless-stopped`, un healthcheck por latido, y logs por cada fallo de envío con el número de intento.
- **[Ventas sigue vendiendo mientras una cancelación está pendiente]** -> Es inherente a la consistencia eventual. La ventana dura lo que ventas esté caído, y en ese tiempo ventas tampoco vende. Lo vendido antes de la confirmación se resuelve con las devoluciones de la Etapa III.
- **[Reservas vigentes de un evento recién cancelado]** -> No se liberan explícitamente: el pago se rechaza y vencen solas con el TTL.
- **[Eventos existentes sin tipo ni organizador]** -> La migración pone `tipo = 'otro'` y deja `organizador_id` nullable en la base. La API lo exige en las altas nuevas.
- **[Desfase de reloj entre servicios]** -> Los dos usan `now()` del mismo PostgreSQL.
- **[El envío inmediato y el cron mandan la misma operación al mismo tiempo]** -> Ventas lo absorbe por versión, y `aplicar` es idempotente.

## Migration Plan

1. **eventos `0002`**: crea `organizadores`, `participantes`, `evento_participantes` y `operaciones_ventas`; agrega a `eventos` las columnas `tipo` (default `'otro'`), `descripcion` (default `''`), `organizador_id` (nullable), `version`, `version_aplicada` (default 0) y `publicado_at` (se completa con `created_at` para los eventos ya publicados); amplía el check de `estado` con `cancelado`. Con su `downgrade`.
2. **ventas `0002`**: agrega las columnas a `inventario_eventos`, con su `downgrade`.
3. **Orden de despliegue**: primero ventas (acepta `fecha_inicio` opcional y el endpoint nuevo), después eventos y `eventos-cron`. Con `docker compose up -d --build` las migraciones se aplican solas al arrancar cada servicio.
4. **Rollback**: `alembic downgrade -1` en cada servicio y volver a la imagen anterior. Las operaciones pendientes del outbox se pierden con el downgrade, y es aceptable en desarrollo.

## Open Questions

- Intervalo y lote del cron por defecto (5 s y 20). Se ajustan por variable de entorno sin cambiar el diseño.
