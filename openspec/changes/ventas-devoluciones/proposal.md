# Propuesta: Devoluciones de tickets en Ventas

## Why

Actualmente el servicio de `ventas` soporta el ciclo completo de compra para ambas modalidades de ticket (asiento específico numerado y zona general no numerada), pero una vez pagada una reserva los tickets quedan vendidos en forma definitiva sin mecanismo de devolución. Es necesario permitir que los clientes soliciten la devolución de tickets comprados y que los administradores las aprueben o rechacen, liberando el asiento o cupo de zona correspondiente cuando una devolución se aprueba.

## What Changes

- **Solicitud de devoluciones por cliente (`services/ventas`)**:
  - Un usuario con rol `cliente` puede solicitar la devolución de un ticket individual perteneciente a una de sus órdenes pagadas, opcionalmente indicando un motivo.
  - La solicitud nace en estado `pendiente` y no libera el ticket hasta ser aprobada por un administrador.
  - No se permite tener más de una solicitud pendiente ni aprobar dos veces la devolución de un mismo ticket vendido en una orden.
- **Gestión de devoluciones por administrador (`services/ventas`)**:
  - Un usuario con rol `administrador` puede listar las solicitudes de devolución (filtrables por estado), aprobarlas o rechazarlas (con motivo/nota opcional).
  - Al **aprobar**, el ticket vuelve atómicamente a estado `disponible` (sin `orden_id`, `reserva_id` ni `reservado_hasta`):
    - En modalidad **numerada**, el asiento específico (`fila`, `numero`) vuelve a quedar seleccionable y reservable.
    - En modalidad **general (por zona)**, el ticket vuelve al pool disponible de la zona, incrementando en 1 el cupo disponible.
  - Al **rechazar**, la solicitud pasa a `rechazada` y el ticket continúa vendido al cliente; el historial conserva el registro de la decisión.
  - La resolución concurrente (dos administradores aprobando/rechazando al mismo tiempo) es segura mediante actualización condicional atómica.
- **Historial de compras y trazabilidad (`services/ventas`)**:
  - `GET /ventas/compras` sigue mostrando las órdenes del cliente (incluso si alguno o todos sus tickets fueron devueltos) e informa para cada ticket si tiene una devolución asociada y su estado (`pendiente`, `aprobada`, `rechazada`), preservando `orden_items` como registro histórico inmutable de la compra.
  - `orden_items` vincula la devolución con la compra concreta (`orden_item_id`) para soportar correctamente que un mismo ticket liberado vuelva a venderse en el futuro en otra orden.
- **Migración de base de datos (`services/ventas`)**:
  - Nueva migración Alembic (`0002_devoluciones`) en `ventas_db` que crea la tabla `devoluciones` con restricciones de integridad y unicidad parcial para solicitudes activas por `orden_item_id`.
- **Frontend (`frontend/`)**:
  - En `Mis compras`, cada ticket comprado muestra su estado de devolución (si existe) o permite solicitar su devolución (con motivo opcional).
  - Nueva vista de administración (`/admin/devoluciones`, visible y accesible para `administrador`) para listar solicitudes y aprobarlas o rechazarlas.
- **Testing**:
  - Tests unitarios, de integración (PostgreSQL de test con rollback) y de concurrencia en `services/ventas`.
  - Tests de componentes/flujos con Vitest + Testing Library + MSW en `frontend/`.

## Capabilities

### New Capabilities
- `ventas/devoluciones`: flujo completo de solicitud de devolución por ticket individual por clientes y aprobación/rechazo por administradores con liberación atómica del asiento numerado o cupo de zona general y control de concurrencia.

### Modified Capabilities
- `ventas/compra-concurrencia`: el historial propio (`GET /ventas/compras`) expone el estado de devolución de cada ticket adquirido y el ciclo de disponibilidad contempla tickets liberados por devolución aprobada para su posterior reventa.

## Impact

- **Código afectado**:
  - `services/ventas/app/models.py`, `services/ventas/app/servicio.py`, `services/ventas/app/routers/ventas.py`.
  - Nueva migración Alembic en `services/ventas/alembic/versions/`.
  - Nuevos tests en `services/ventas/tests/`.
  - `frontend/src/App.jsx`, `frontend/src/pages/Compras.jsx`, nueva página `frontend/src/pages/AdminDevoluciones.jsx` y tests en `frontend/src/pages/`.
- **APIs externas (vía gateway, bajo `/api/ventas/*` ya enrutado)**:
  - `POST /api/ventas/devoluciones` (cliente): crear solicitud de devolución para un ticket comprado.
  - `GET /api/ventas/devoluciones` (cliente: las propias; administrador: todas, con filtro opcional `?estado=`).
  - `POST /api/ventas/devoluciones/{id}/aprobar` (administrador): aprobar y liberar ticket.
  - `POST /api/ventas/devoluciones/{id}/rechazar` (administrador): rechazar solicitud.
  - `GET /api/ventas/compras` (cliente): se enriquece cada ticket con `orden_item_id`, `tipo_zona` y `devolucion` (nullable).
- **Gateway**: no requiere cambios de ruteo porque `/api/ventas/{resto:path}` ya reenvía todo el prefijo `/ventas/*` con `X-User-Id` y `X-User-Role`.
- **Dependencias**: sin nuevas librerías ni servicios externos; opera únicamente sobre `ventas_db` (sin consultar al servicio `eventos`).
