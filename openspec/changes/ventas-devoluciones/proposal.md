# Propuesta: Devoluciones de tickets en Ventas

## Why

Actualmente el servicio de `ventas` soporta el ciclo completo de compra para ambas modalidades de ticket (asiento específico numerado y zona general no numerada) y recibe el ciclo de vida del evento (`fecha_inicio`, `cancelado`) desde `eventos`, pero una vez pagada una reserva los tickets quedan vendidos en forma definitiva sin mecanismo de devolución. Es necesario permitir que los clientes soliciten la devolución de tickets comprados y que los administradores las aprueben o rechacen —respetando si el evento fue cancelado o ya comenzó—, liberando el asiento o cupo de zona correspondiente cuando una devolución se aprueba, y aprovechando en `ventas` y `frontend` la información de estado del evento que ya llega a `ventas_db`.

## What Changes

- **Solicitud de devoluciones por cliente (`services/ventas`)**:
  - Un usuario con rol `cliente` puede solicitar la devolución de un ticket individual perteneciente a una de sus órdenes pagadas, opcionalmente indicando un motivo.
  - La solicitud nace en estado `pendiente` y no libera el ticket hasta ser aprobada por un administrador.
  - No se permite tener más de una solicitud pendiente ni aprobar dos veces la devolución de un mismo ticket vendido en una orden.
  - **Interacción con el ciclo de vida del evento**: se rechazan con `409` las nuevas solicitudes sobre eventos que ya comenzaron (`fecha_inicio <= now()` y no cancelados); en cambio, si el evento está `cancelado`, se permite solicitar y aprobar devoluciones incluso después de la fecha original.
- **Gestión de devoluciones por administrador (`services/ventas`)**:
  - Un usuario con rol `administrador` puede listar las solicitudes de devolución (filtrables por estado), viendo además la fecha y si el evento está cancelado (`evento_fecha_inicio`, `evento_cancelado`), y aprobarlas o rechazarlas (con motivo/nota opcional).
  - Al **aprobar**, el ticket vuelve atómicamente a estado `disponible` (sin `orden_id`, `reserva_id` ni `reservado_hasta`):
    - En modalidad **numerada**, el asiento específico (`fila`, `numero`) vuelve a quedar seleccionable y reservable (si el evento no está cancelado ni iniciado).
    - En modalidad **general (por zona)**, el ticket vuelve al pool disponible de la zona, incrementando en 1 el cupo disponible.
  - Al **rechazar**, la solicitud pasa a `rechazada` y el ticket continúa vendido al cliente; el historial conserva el registro de la decisión.
  - La resolución concurrente (dos administradores aprobando/rechazando al mismo tiempo) es segura mediante actualización condicional atómica.
- **Historial de compras, disponibilidad y trazabilidad (`services/ventas`)**:
  - `GET /ventas/compras` sigue mostrando las órdenes del cliente (incluso si alguno o todos sus tickets fueron devueltos), informa para cada ticket su estado de devolución (`pendiente`, `aprobada`, `rechazada`) y expone el estado local del evento (`evento_fecha_inicio`, `evento_cancelado`, `evento_estado`), preservando `orden_items` como registro histórico inmutable de la compra.
  - `orden_items` vincula la devolución con la compra concreta (`orden_item_id`) para soportar correctamente que un mismo ticket liberado vuelva a venderse en el futuro en otra orden.
  - `GET /ventas/eventos/{evento_id}/disponibilidad` agrega el campo informativo `a_la_venta` (`bool`) calculado desde `inventario_eventos`.
- **Migración de base de datos (`services/ventas`)**:
  - Nueva migración Alembic (`0003_devoluciones`, sobre `0002_estado_del_evento`) en `ventas_db` que crea la tabla `devoluciones` con restricciones de integridad y unicidad parcial para solicitudes activas por `orden_item_id`.
- **Frontend (`frontend/`)**:
  - En `Mis compras`, cada compra muestra la fecha y estado del evento (cancelado/finalizado), cada ticket muestra su estado de devolución y permite solicitar devolución (con motivo opcional), deshabilitando la solicitud si el evento finalizó y no fue cancelado.
  - Nueva vista de administración (`/admin/devoluciones`, protegida reutilizando `<SoloRol roles={["administrador"]}>` en `App.jsx`) para listar solicitudes con visibilidad de eventos cancelados y aprobarlas o rechazarlas.
- **Testing**:
  - Tests unitarios, de integración (PostgreSQL de test con rollback) y de concurrencia en `services/ventas`.
  - Tests de componentes/flujos con Vitest + Testing Library + MSW en `frontend/`.

## Capabilities

### New Capabilities
- `ventas/devoluciones`: flujo completo de solicitud de devolución por ticket individual por clientes (respetando eventos cancelados vs. finalizados) y aprobación/rechazo por administradores con liberación atómica del asiento numerado o cupo de zona general y control de concurrencia.

### Modified Capabilities
- `ventas/compra-concurrencia`: `GET /ventas/eventos/{evento_id}/disponibilidad` informa `a_la_venta` y contempla tickets liberados por devolución aprobada; el historial propio (`GET /ventas/compras`) expone el estado de devolución de cada ticket adquirido y el estado local del evento (`evento_fecha_inicio`, `evento_cancelado`, `evento_estado`).

## Impact

- **Código afectado**:
  - `services/ventas/app/models.py`, `services/ventas/app/servicio.py`, `services/ventas/app/routers/ventas.py`.
  - Nueva migración Alembic `0003_devoluciones.py` en `services/ventas/alembic/versions/`.
  - Nuevos tests en `services/ventas/tests/`.
  - `frontend/src/App.jsx`, `frontend/src/pages/Compras.jsx`, nueva página `frontend/src/pages/AdminDevoluciones.jsx` y tests en `frontend/src/pages/`.
- **APIs externas (vía gateway, bajo `/api/ventas/*` ya enrutado)**:
  - `POST /api/ventas/devoluciones` (cliente): crear solicitud de devolución para un ticket comprado.
  - `GET /api/ventas/devoluciones` (cliente: las propias; administrador: todas, con filtro opcional `?estado=`, incluyendo `evento_fecha_inicio` y `evento_cancelado`).
  - `POST /api/ventas/devoluciones/{id}/aprobar` (administrador): aprobar y liberar ticket.
  - `POST /api/ventas/devoluciones/{id}/rechazar` (administrador): rechazar solicitud.
  - `GET /api/ventas/compras` (cliente): se enriquece cada ticket con `orden_item_id`, `tipo_zona`, `devolucion` (nullable), `evento_fecha_inicio`, `evento_cancelado` y `evento_estado`.
  - `GET /api/ventas/eventos/{evento_id}/disponibilidad` (público): agrega `a_la_venta: bool`.
- **Gateway**: no requiere cambios de ruteo porque `/api/ventas/{resto:path}` ya reenvía todo el prefijo `/ventas/*` con `X-User-Id` y `X-User-Role`.
- **Dependencias**: sin nuevas librerías ni servicios externos; opera únicamente sobre `ventas_db` (sin consultar al servicio `eventos`).
