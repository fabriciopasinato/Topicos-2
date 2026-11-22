# Tasks: Devoluciones de tickets en Ventas

## 1. Modelo de datos y migración Alembic (`services/ventas`)

- [ ] 1.1 Agregar el modelo `Devolucion` (y constantes de estado `DEVOLUCION_PENDIENTE`, `DEVOLUCION_APROBADA`, `DEVOLUCION_RECHAZADA`) en `services/ventas/app/models.py` con FK a `orden_items.id`, `ordenes.id` y `tickets.id`, check constraint de estados e índice único parcial `uq_devoluciones_item_activa` sobre `(orden_item_id) WHERE estado IN ('pendiente', 'aprobada')`.
- [ ] 1.2 Crear la migración Alembic `services/ventas/alembic/versions/0002_devoluciones.py` (`down_revision = "0001"`) para crear y revertir la tabla `devoluciones` y sus índices, y ampliar `services/ventas/tests/test_migraciones.py` para verificar `upgrade`/`downgrade` con la nueva tabla y sus restricciones.

## 2. Lógica de negocio en `services/ventas`

- [ ] 2.1 Implementar en `services/ventas/app/servicio.py` las operaciones `solicitar_devolucion`, `listar_devoluciones`, `aprobar_devolucion` y `rechazar_devolucion` con actualizaciones condicionales atómicas (liberando el asiento específico o el ticket del pool general al aprobar) y manejo de errores (`NoEncontrado`, `DevolucionYaExiste`, `DevolucionYaResuelta`, `Invalido`), más tests unitarios/de integración en `services/ventas/tests/test_devoluciones.py`.
- [ ] 2.2 Actualizar `compras_de` en `services/ventas/app/servicio.py` para incluir `orden_item_id`, `tipo_zona` y `devolucion` (última devolución del ítem o `None`) manteniendo todos los campos previos y conservando los ítems ya devueltos; actualizar/ampliar tests en `services/ventas/tests/test_pago_idempotencia_historial.py`.

## 3. Endpoints HTTP y autorización en `services/ventas`

- [ ] 3.1 Exponer en `services/ventas/app/routers/ventas.py` los endpoints `POST /ventas/devoluciones` (`cliente`), `GET /ventas/devoluciones` (`cliente` y `administrador`, con filtro opcional `estado`), `POST /ventas/devoluciones/{devolucion_id}/aprobar` (`administrador`) y `POST /ventas/devoluciones/{devolucion_id}/rechazar` (`administrador`), con esquemas Pydantic y mapeo de errores HTTP (`403`, `404`, `409`, `422`), cubiertos por tests de integración en `services/ventas/tests/test_devoluciones.py`.

## 4. Pruebas de concurrencia y ciclo de liberación por modalidad (`services/ventas`)

- [ ] 4.1 Agregar tests de integración y concurrencia (con sesiones paralelas en PostgreSQL de test) en `services/ventas/tests/test_concurrencia.py` y `services/ventas/tests/test_devoluciones.py` cubriendo: dos solicitudes simultáneas sobre el mismo `orden_item_id`, dos administradores resolviendo la misma devolución en simultáneo (aprobar/aprobar y aprobar/rechazar), liberación de asiento numerado y reventa + segunda devolución, y liberación de entrada en zona general con incremento de cupo y recompra.

## 5. Frontend (`frontend/`)

- [ ] 5.1 Actualizar `frontend/src/pages/Compras.jsx` para mostrar la modalidad del ticket, el estado/nota de su devolución y permitir al cliente solicitar devolución (con motivo opcional) para ítems sin devolución activa o rechazados previamente; actualizar y ampliar `frontend/src/pages/Compras.test.jsx` con MSW.
- [ ] 5.2 Crear `frontend/src/pages/AdminDevoluciones.jsx` y registrar la ruta `/admin/devoluciones` (con guarda `SoloAdmin` y enlace en `Encabezado` visible solo para `administrador`) en `frontend/src/App.jsx`, con filtro por estado y acciones de aprobar/rechazar con nota opcional; agregar tests con Vitest + MSW en `frontend/src/pages/AdminDevoluciones.test.jsx`.

## 6. Verificación integral y CI

- [ ] 6.1 Verificar que `.github/workflows/tests.yml` ejecute los nuevos tests de `services/ventas` (pytest) y `frontend` (Vitest) en cada PR, y correr localmente la suite completa de tests de `services/ventas` y `frontend` confirmando que todo pasa sin regresiones.
