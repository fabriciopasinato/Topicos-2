# Design: Devoluciones de tickets en Ventas

## Context

Ver [proposal.md](./proposal.md) para la motivación.

Actualmente `services/ventas` modela el inventario con un registro en `tickets` por cada entrada vendible (`tipo_zona = 'numerada'` con `fila`/`numero`, o `tipo_zona = 'general'` con `fila = NULL, numero = NULL`). Al pagar una reserva se crea una `Orden`, se pasan sus tickets a `estado = 'vendido'` con `orden_id` y se crean filas en `orden_items (id, orden_id, ticket_id, precio)`. El gateway ya reenvía todo `/api/ventas/{resto:path}` hacia `ventas` inyectando `X-User-Id` y `X-User-Role`.

## Goals / Non-Goals

**Goals:**
- Permitir solicitudes de devolución por ticket individual (`orden_item_id`) para clientes y su resolución (`aprobar` / `rechazar`) por administradores.
- Garantizar atomicidad y ausencia de condiciones de carrera al crear solicitudes duplicadas o resolver la misma solicitud en simultáneo.
- Preservar la trazabilidad histórica de compras y devoluciones aun cuando un ticket liberado vuelva a venderse en una orden futura.
- Mantener el desacople total entre `ventas` y `eventos`.
- Exponer la funcionalidad completa en el frontend (vista de cliente y vista de administrador).

**Non-Goals:**
- Integración con pasarelas de pago reales (el reembolso monetario es simulado, coherente con el pago simulado).
- Notificaciones asíncronas por correo o colas RabbitMQ (corresponden a una etapa posterior).
- Modificación de las reglas actuales de límite o TTL por modalidad en la creación de reservas.

## Decisions

### 1. Vincular devoluciones a `orden_item_id` (y no solo a `ticket_id`)
- **Decisión**: la tabla `devoluciones` referencia `orden_item_id` (FK a `orden_items.id`), además de almacenar `orden_id`, `ticket_id` y `user_id`.
- **Motivo**: un ticket devuelto vuelve a quedar `disponible` y puede comprarse nuevamente en otra orden, generando un nuevo `orden_items.id`. Vincular la devolución al `orden_item_id` permite conservar intacto el historial de cada venta y distinguir la compra original de reventas posteriores sin reutilizar ni pisar registros.
- **Alternativa descartada**: referenciar solo `ticket_id` con unique constraint sobre `ticket_id`, lo que impediría devolver un asiento que ya fue devuelto y revendido previamente.

### 2. Unicidad parcial en PostgreSQL para evitar solicitudes duplicadas bajo concurrencia
- **Decisión**: crear el índice único parcial `uq_devoluciones_item_activa` sobre `devoluciones (orden_item_id) WHERE estado IN ('pendiente', 'aprobada')`.
- **Motivo**:
  - Impide a nivel de base de datos que dos solicitudes concurrentes del cliente generen dos devoluciones pendientes para el mismo ítem.
  - Impide solicitar una nueva devolución sobre un ítem cuya devolución ya fue aprobada.
  - Permite que, si una solicitud fue `rechazada`, el cliente pueda enviar una nueva solicitud mientras se conserva el registro de la rechazada.
- **Alternativa descartada**: validar solo con un `SELECT` previo en Python (susceptible a race conditions bajo peticiones simultáneas).

### 3. Esquema de la tabla `devoluciones` (migración Alembic `0002_devoluciones`)
Columnas:
- `id`: `Integer` PK
- `orden_item_id`: `Integer` FK `orden_items.id` (NOT NULL, indexado)
- `orden_id`: `Integer` FK `ordenes.id` (NOT NULL, indexado)
- `ticket_id`: `Integer` FK `tickets.id` (NOT NULL, indexado)
- `user_id`: `Integer` (NOT NULL, indexado)
- `estado`: `String(20)` NOT NULL, default `'pendiente'`, `CheckConstraint("estado IN ('pendiente', 'aprobada', 'rechazada')")`
- `motivo`: `String(500)` NULL (opcional, enviado por el cliente)
- `nota_resolucion`: `String(500)` NULL (opcional, enviada por el administrador)
- `resuelto_por`: `Integer` NULL (`user_id` del administrador)
- `resuelto_at`: `DateTime(timezone=True)` NULL
- `created_at`: `DateTime(timezone=True)` NOT NULL `server_default=func.now()`

Índices:
- `uq_devoluciones_item_activa` UNIQUE sobre `(orden_item_id) WHERE estado IN ('pendiente', 'aprobada')`
- `ix_devoluciones_estado_created` sobre `(estado, created_at)` para el listado de administración.

### 4. Actualización condicional atómica en aprobación y rechazo
- **Aprobar**:
  1. `UPDATE devoluciones SET estado = 'aprobada', resuelto_por = :admin_id, nota_resolucion = :nota, resuelto_at = now() WHERE id = :id AND estado = 'pendiente' RETURNING id, ticket_id, orden_id`.
  2. Si no devuelve fila: verificar existencia (`404` si no existe, `409` si ya estaba resuelta).
  3. `UPDATE tickets SET estado = 'disponible', reserva_id = NULL, reservado_hasta = NULL, orden_id = NULL WHERE id = :ticket_id AND orden_id = :orden_id AND estado = 'vendido' RETURNING id`.
  4. Si el ticket no se actualizó (defensivo), hacer `rollback` y responder `409`.
  5. `commit`.
- **Rechazar**:
  1. `UPDATE devoluciones SET estado = 'rechazada', resuelto_por = :admin_id, nota_resolucion = :nota, resuelto_at = now() WHERE id = :id AND estado = 'pendiente' RETURNING id`.
  2. Si no devuelve fila: `404` si no existe, `409` si ya estaba resuelta.
  3. `commit` (no modifica `tickets`).
- **Liberación diferenciada por modalidad**:
  - En zona `numerada`, el registro de `tickets` conserva `(fila, numero)`, por lo que al volver a `estado = 'disponible'` ese asiento específico reaparece disponible en el mapa.
  - En zona `general`, el registro de `tickets` tiene `fila = NULL, numero = NULL`, por lo que al volver a `estado = 'disponible'` incrementa en 1 el cupo disponible de la zona y vuelve a ser elegible por `FOR UPDATE SKIP LOCKED`.

### 5. Contrato HTTP y comunicación entre servicios
- **Comunicación `frontend -> gateway`**: sync (HTTP REST).
- **Comunicación `gateway -> ventas`**: sync (HTTP REST). Se reutiliza el proxy existente `/api/ventas/{resto:path}` -> `/ventas/{resto}` con los headers `X-User-Id` y `X-User-Role` inyectados por el gateway. No se requieren cambios en `gateway`.
- **Comunicación `ventas -> eventos` / `ventas -> auth`**: ninguna (ni sync ni async). `ventas` resuelve todo con su propia base `ventas_db`.

Endpoints en `services/ventas`:
- `POST /ventas/devoluciones` (`cliente`): body `{ "orden_item_id": int, "motivo": str | null }`. Responde `201` con el detalle de la devolución.
- `GET /ventas/devoluciones` (`cliente` o `administrador`): query opcional `estado` (`pendiente` | `aprobada` | `rechazada`). El cliente ve solo las suyas; el administrador ve todas.
- `POST /ventas/devoluciones/{devolucion_id}/aprobar` (`administrador`): body opcional `{ "nota": str | null }`. Responde `200`.
- `POST /ventas/devoluciones/{devolucion_id}/rechazar` (`administrador`): body opcional `{ "nota": str | null }`. Responde `200`.
- `GET /ventas/compras` (`cliente`): mantiene los campos existentes de cada ticket y agrega `orden_item_id`, `tipo_zona` y `devolucion` (última devolución del ítem o `null`).

### 6. Diseño del Frontend
- `frontend/src/pages/Compras.jsx`:
  - Muestra cada ticket con su modalidad (`Asiento A-1` o `Entrada general`) y, si tiene `devolucion`, su estado (`pendiente`, `aprobada`, `rechazada`) y nota de resolución si existe.
  - Si no tiene devolución o la última fue `rechazada`, muestra un flujo simple para ingresar un motivo opcional y confirmar `Solicitar devolución` (`POST /api/ventas/devoluciones`), actualizando la vista.
- `frontend/src/pages/AdminDevoluciones.jsx`:
  - Ruta `/admin/devoluciones` protegida por rol `administrador` (en `App.jsx` con componente `SoloAdmin`, y enlace `Devoluciones` en `Encabezado` visible solo si `usuario.rol === "administrador"`).
  - Permite filtrar por estado (por defecto `pendiente`), ver cliente (`user_id`), orden, evento, zona, modalidad/asiento, precio y motivo, e ingresar una nota opcional para `Aprobar` o `Rechazar`.

## Risks / Trade-offs

- **[Riesgo] `GET /ventas/compras` cambia de forma aditiva** → Mitigación: se conservan todos los campos previos (`ticket_id`, `evento_id`, `zona_id`, `fila`, `numero`, `precio`) y solo se agregan `orden_item_id`, `tipo_zona` y `devolucion` (nullable), manteniendo compatibilidad con tests y clientes existentes.
- **[Riesgo] Reenvío concurrente de `POST /ventas/devoluciones`** → Mitigación: el índice único parcial `uq_devoluciones_item_activa` convierte cualquier carrera en un error de integridad capturado y devuelto como `409`.
- **[Riesgo] Aprobación concurrente con otro administrador** → Mitigación: el `UPDATE ... WHERE id = :id AND estado = 'pendiente'` en PostgreSQL serializa la transición de estado a nivel de fila y asegura que solo una operación gane.
- **[Trade-off] Un administrador no ve el nombre del evento ni email del usuario en `ventas_db`** → Mitigación: `ventas` muestra los identificadores propios (`evento_id`, `zona_id`, `user_id`, `fila`, `numero`, `precio`) preservando el aislamiento de microservicios sin acoplar `ventas` a `eventos` ni `auth`.

## Migration Plan

1. Aplicar migración Alembic `0002_devoluciones` en `services/ventas` (se ejecuta automáticamente en el arranque del contenedor vía `entrypoint.sh` y en la fixture de tests).
2. Rollback: `alembic downgrade 0001` elimina únicamente la tabla `devoluciones` y sus índices sin alterar `tickets`, `ordenes` ni `orden_items`.
