# Tasks

## 1. Ventas: fecha de inicio, actualización versionada y cierre de la venta

- [ ] 1.1 Crear la migración Alembic `0002` de ventas, que agrega a `inventario_eventos` las columnas `fecha_inicio` (nullable), `cancelado` (default false) y `version` (default 0), con su `downgrade`, y reflejarlas en `app/models.py`. Verificar con un test de integración que la migración aplica y revierte, y que un inventario existente queda con `fecha_inicio` nula, `cancelado` falso y `version` 0.
- [ ] 1.2 Aceptar `fecha_inicio` opcional en `POST /internal/inventario` y guardarla. Verificar con tests: inventario con fecha que queda guardada, inventario sin fecha que se recibe como antes, y reenvío sin duplicar tickets ni cambiar la fecha.
- [ ] 1.3 Implementar `PUT /internal/eventos/{evento_id}` con el UPDATE condicional por versión del design (cancelación irreversible, 200 cuando ignora y 404 si no hay inventario). Verificar con tests: cambio de fecha, reenvío de la misma versión, versión vieja que llega tarde, reprogramación posterior a una cancelación, evento inexistente, y que la ruta no es alcanzable a través del gateway.
- [ ] 1.4 Agregar a `reservar` y `pagar` la lectura de `inventario_eventos` con `FOR SHARE` y el 409 si el evento está cancelado o `fecha_inicio <= now()`. Verificar con tests: reserva de un evento cancelado, reserva de un evento iniciado, pago de una reserva de un evento cancelado después, evento sin fecha que sigue vendiendo, y un test de concurrencia de reserva contra cancelación simultáneas en el que nunca se vende una entrada del evento cancelado.

## 2. Eventos: modelo de datos

- [ ] 2.1 Crear la migración Alembic `0002` de eventos según el Migration Plan del design (`organizadores`, `participantes`, `evento_participantes`, `operaciones_ventas` con su índice parcial; en `eventos`: `tipo`, `descripcion`, `organizador_id`, `version`, `version_aplicada`, `publicado_at`, y el check de `estado` con `cancelado`), con su `downgrade`, y reflejarla en `app/models.py` con el `StrEnum` de tipos. Verificar con un test de integración que la migración aplica y revierte, que un evento publicado existente queda con `tipo = 'otro'` y `publicado_at` completo, y que el check rechaza un tipo inexistente.
- [ ] 2.2 Implementar `buscar_o_crear(session, Modelo, nombre)` con la normalización de nombres y el `INSERT ... ON CONFLICT DO NOTHING`. Verificar con tests unitarios de la normalización (mayúsculas, espacios sobrantes e internos), un test de integración de reutilización por nombre, el nombre vacío con error, y un test de concurrencia con dos altas simultáneas del mismo organizador que dejan una sola fila.

## 3. Eventos: clasificación, edición y cartelera

- [ ] 3.1 Ampliar `POST /eventos` con `tipo`, `organizador`, `participantes` y `descripcion`, y las respuestas de detalle y resumen con la clasificación y el estado calculado (`finalizado` según `now()` de la base). Verificar con tests: alta completa, alta sin tipo o sin organizador con 422, tipo inexistente con 422, participante repetido guardado una sola vez, publicado a futuro informado `publicado`, publicado con fecha pasada informado `finalizado`, y borrador con fecha pasada que sigue `borrador`.
- [ ] 3.2 Restringir `PATCH /eventos/{id}` a datos descriptivos según el requisito de edición: 422 si llega `fecha`, `recinto_id` solo en borrador (409 si está publicado), y 409 si el evento está finalizado o cancelado. Verificar con tests para cada caso, más la edición de descripción y participantes de un evento publicado sin ninguna llamada a ventas (ventas simulado que falla si lo llaman).
- [ ] 3.3 Agregar a la cartelera los filtros `tipo`, `desde` y `hasta`, excluir eventos finalizados, y la visibilidad de los cancelados según `publicado_at`. Verificar con tests: listado solo con publicados futuros, filtro por tipo, filtro por rango, combinación de filtros, filtro inválido con 422, detalle público de un evento cancelado tras publicarse, y 404 para un borrador cancelado.
- [ ] 3.4 Enviar `fecha_inicio` en el inventario al publicar, registrar `publicado_at`, y rechazar con 422 la publicación de un evento con fecha pasada. Verificar actualizando los tests de publicación existentes (ventas simulado que recibe la fecha) y agregando el caso de fecha pasada.

## 4. Eventos: ciclo de vida y outbox

- [ ] 4.1 Implementar `DELETE /eventos/{id}`, solo en borrador, con borrado en cascada de sectores, zonas, asientos y participantes asociados. Verificar con tests: borrado de un borrador con 204, 409 para publicado y cancelado, 403 para un owner ajeno y para un cliente, y que los organizadores y participantes compartidos con otros eventos siguen existiendo.
- [ ] 4.2 Implementar en `cliente_ventas` el envío de `PUT /internal/eventos/{id}`, con el mismo timeout y manejo de errores que el envío de inventario. Verificar con tests de cliente usando un transporte simulado: éxito, timeout, error 5xx y 404.
- [ ] 4.3 Implementar `aplicar(op)` (lock del evento, solo si `op.version > version_aplicada`, nunca sobre un evento cancelado, y actualización de `version_aplicada`). Verificar con tests unitarios y de integración: aplicación normal, operación repetida sin efecto, operación vieja ignorada, y reprogramación posterior a una cancelación aplicada que no la revierte.
- [ ] 4.4 Implementar `POST /eventos/{id}/cancelar`: directo en borrador; en publicado, TX1 con versión y outbox, envío inmediato, y 200 o 202; 200 sin operación nueva si ya está cancelado; 409 si está finalizado. Verificar con tests usando ventas simulado: borrador cancelado, publicado con ventas disponible, publicado con ventas caído (202, sigue `publicado` y el detalle del owner muestra la operación pendiente), cancelación repetida, finalizado con 409, y permisos (owner ajeno, cliente, administrador).
- [ ] 4.5 Implementar `POST /eventos/{id}/reprogramar`: directo en borrador; en publicado, por outbox; 422 si la fecha es pasada; 409 si está finalizado, cancelado o tiene una cancelación pendiente (también para `PATCH`). Verificar con tests: reprogramación de un borrador, de un publicado con ventas disponible y con ventas caído (conserva la fecha anterior), fecha pasada, cancelación pendiente que bloquea la reprogramación y la edición, y un test de concurrencia de reprogramación y cancelación simultáneas que asigna versiones distintas y termina `cancelado`.

## 5. Eventos: proceso `eventos-cron`

- [ ] 5.1 Implementar `app/cron.py` con un ciclo que toma operaciones pendientes vencidas con `FOR UPDATE SKIP LOCKED`, las envía, aplica y confirma, o posterga con espera exponencial hasta 60 s y registra el error; actualiza el archivo de latido al final de cada ciclo; y lee `CRON_INTERVALO_SEGUNDOS` y `CRON_LOTE` de la configuración. Verificar con tests de integración que ejecutan un ciclo: pendiente confirmada cuando ventas vuelve, pendiente postergada cuando sigue caído, la falla entre la confirmación de ventas y el registro en eventos resuelta en el ciclo siguiente, dos reprogramaciones pendientes que terminan con la última fecha en los dos lados, y dos ciclos concurrentes que no envían la misma operación a la vez.
- [ ] 5.2 Agregar el servicio `eventos-cron` a `docker-compose.yml` (imagen de eventos, comando `python -m app.cron`, credenciales de `eventos_db`, `VENTAS_URL`, sin puertos, `restart: unless-stopped`, healthcheck por antigüedad del latido, y `depends_on: eventos` healthy) y las variables nuevas a `.env.example`. Verificar con `docker compose config`, y levantando el stack: `eventos-cron` llega a healthy; con `ventas` detenido arranca igual; y al matar el proceso Docker lo reinicia.
- [ ] 5.3 Actualizar el `README.md` con el contenedor `eventos-cron` en la tabla de componentes y en el orden de arranque, y cómo ver sus logs. Verificar siguiendo el README.

## 6. Frontend del event owner

- [ ] 6.1 Traer `dev` a la rama si el change de auth ya está mergeado y reutilizar `SoloRol`; si no, agregar una protección de rutas por rol equivalente. Crear la vista "Mis eventos" bajo `/owner`, con estado (incluido `finalizado`) y operaciones pendientes. Verificar con tests de componentes usando MSW: listado, acceso denegado para un cliente, y aviso de operación pendiente.
- [ ] 6.2 Implementar el formulario de alta y edición del evento (nombre, fecha solo en el alta, recinto solo en borrador, tipo, organizador, participantes y descripción) con manejo de 422 y 409. Verificar con tests de componentes usando MSW.
- [ ] 6.3 Implementar el armado de sectores y zonas (numerada con filas y asientos por fila, general con capacidad, precio) y el borrado de zonas en borrador, más el botón de publicar con manejo de 503 y 422. Verificar con tests de componentes usando MSW.
- [ ] 6.4 Implementar reprogramar, cancelar (con confirmación) y borrar, mostrando el resultado 200 o el aviso de "en proceso" del 202. Verificar con tests de componentes usando MSW.
- [ ] 6.5 Agregar a la cartelera pública los filtros por tipo y rango de fechas, y mostrar tipo, organizador y participantes en el detalle, con el aviso de evento cancelado o finalizado. Verificar con tests de componentes usando MSW, actualizando los tests existentes de cartelera y detalle.

## 7. Verificación integrada

- [ ] 7.1 Verificar que el CI existente corre los tests nuevos de eventos (incluidos los del cron) y de ventas, y los del frontend, y que su validación de `docker compose config` incluye `eventos-cron`. Verificar con el PR en verde.
- [ ] 7.2 Con el stack levantado por `docker compose up -d`, recorrer de punta a punta: un owner crea un evento con clasificación, arma zonas y lo publica; un cliente filtra la cartelera y reserva; el owner lo reprograma y ventas cierra la venta en la nueva fecha; con `ventas` detenido el owner lo cancela y recibe 202; al levantar `ventas`, el cron completa la cancelación y una reserva nueva recibe 409; y un borrador se borra. Verificar también que todas esas solicitudes figuran en la bitácora de `gateway_db`.

## Workflow follow-up

- Abrir el PR de `feature/eventos-catalogo-ampliado` a `dev` con el CI en verde y la revisión del integrante a cargo de ventas.
- Archivar el change con `/opsx:archive` y sincronizar las specs principales.
