# Tasks: Devoluciones de tickets en Ventas

## 1. Modelo de datos y migración Alembic (`services/ventas`)

- [x] 1.1 Agregar el modelo `Devolucion` (y constantes de estado `DEVOLUCION_PENDIENTE`, `DEVOLUCION_APROBADA`, `DEVOLUCION_RECHAZADA`) en `services/ventas/app/models.py` con FK a `orden_items.id`, `ordenes.id` y `tickets.id`, check constraint de estados e índice único parcial `uq_devoluciones_item_activa` sobre `(orden_item_id) WHERE estado IN ('pendiente', 'aprobada')`.
- [x] 1.2 Crear la migración Alembic `services/ventas/alembic/versions/0003_devoluciones.py` (`down_revision = "0002"`) para crear y revertir la tabla `devoluciones` y sus índices, y ampliar `services/ventas/tests/test_migraciones.py` para verificar `upgrade`/`downgrade` (hasta `0002` y `head`) con la nueva tabla y sus restricciones.

## 2. Lógica de negocio en `services/ventas`

- [x] 2.1 Implementar en `services/ventas/app/servicio.py` las operaciones `solicitar_devolucion`, `listar_devoluciones`, `aprobar_devolucion` y `rechazar_devolucion` con validación de ciclo de vida del evento (`FOR SHARE` sobre `inventario_eventos`: rechazar con `409` si finalizó y no está cancelado; permitir siempre si está cancelado o sin fecha), actualizaciones condicionales atómicas (liberando el asiento específico o el ticket del pool general al aprobar), datos `evento_fecha_inicio` y `evento_cancelado` en listados y manejo de errores (`NoEncontrado`, `DevolucionYaExiste`, `DevolucionYaResuelta`, `EventoFinalizado`, `Invalido`), más tests unitarios/de integración en `services/ventas/tests/test_devoluciones.py`.
- [x] 2.2 Actualizar `compras_de` en `services/ventas/app/servicio.py` para incluir `orden_item_id`, `tipo_zona`, `evento_fecha_inicio`, `evento_cancelado`, `evento_estado` (`activo` | `cancelado` | `finalizado`) y `devolucion` (última devolución del ítem o `None`) manteniendo todos los campos previos y conservando los ítems ya devueltos; actualizar `disponibilidad` para incluir `a_la_venta: bool`; actualizar/ampliar tests en `services/ventas/tests/test_pago_idempotencia_historial.py`, `services/ventas/tests/test_inventario_y_disponibilidad.py` y `services/ventas/tests/test_cierre_venta.py`.

## 3. Endpoints HTTP y autorización en `services/ventas`

- [x] 3.1 Exponer en `services/ventas/app/routers/ventas.py` los endpoints `POST /ventas/devoluciones` (`cliente`), `GET /ventas/devoluciones` (`cliente` y `administrador`, con filtro opcional `estado`), `POST /ventas/devoluciones/{devolucion_id}/aprobar` (`administrador`) y `POST /ventas/devoluciones/{devolucion_id}/rechazar` (`administrador`), actualizar `GET /ventas/eventos/{evento_id}/disponibilidad` para devolver `a_la_venta`, con esquemas Pydantic y mapeo de errores HTTP (`403`, `404`, `409`, `422`), cubiertos por tests de integración en `services/ventas/tests/test_devoluciones.py`.

## 4. Pruebas de concurrencia y ciclo de liberación por modalidad (`services/ventas`)

- [x] 4.1 Agregar tests de integración y concurrencia (con sesiones paralelas en PostgreSQL de test) en `services/ventas/tests/test_concurrencia.py` y `services/ventas/tests/test_devoluciones.py` cubriendo: dos solicitudes simultáneas sobre el mismo `orden_item_id`, dos administradores resolviendo la misma devolución en simultáneo (aprobar/aprobar y aprobar/rechazar), liberación de asiento numerado y reventa + segunda devolución, liberación de entrada en zona general con incremento de cupo y recompra, y devolución sobre evento cancelado vs. evento finalizado.

## 5. Frontend (`frontend/`)

- [x] 5.1 Actualizar `frontend/src/pages/Compras.jsx` para mostrar la modalidad del ticket, fecha/estado del evento (`cancelado`, `finalizado`), el estado/nota de su devolución y permitir al cliente solicitar devolución (con motivo opcional) para ítems sin devolución activa o rechazados previamente cuando el evento no esté finalizado; actualizar y ampliar `frontend/src/pages/Compras.test.jsx` con MSW.
- [x] 5.2 Crear `frontend/src/pages/AdminDevoluciones.jsx` y registrar la ruta `/admin/devoluciones` reutilizando `<SoloRol roles={["administrador"]}>` y enlace `Devoluciones` en `Encabezado` visible solo para `administrador` en `frontend/src/App.jsx`, con filtro por estado, visibilidad de eventos cancelados/fecha y acciones de aprobar/rechazar con nota opcional; agregar tests con Vitest + MSW en `frontend/src/pages/AdminDevoluciones.test.jsx`.

## 6. Verificación integral y CI

- [x] 6.1 Verificar que `.github/workflows/tests.yml` ejecute los nuevos tests de `services/ventas` (pytest) y `frontend` (Vitest) en cada PR, y correr localmente la suite completa de tests de `services/ventas` y `frontend` confirmando que todo pasa sin regresiones.
