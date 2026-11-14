# Propuesta: catálogo ampliado y ciclo de vida de eventos

## Why

El servicio de eventos de la Etapa I solo guarda nombre, fecha, recinto y estado, y un evento únicamente puede pasar de borrador a publicado. Eso deja tres huecos:

- **Faltan los datos que necesitan las etapas siguientes.** La búsqueda de la Etapa III ("por tipo, organizador, participante y fecha") y las recomendaciones de la Etapa II ("según preferencias del cliente") no se pueden construir si el evento no tiene tipo, organizador ni participantes.
- **El ciclo de vida está incompleto.** Un evento no se puede cancelar ni reprogramar, un borrador no se puede borrar, y ventas no conoce la fecha del evento, así que podría vender entradas para un evento que ya empezó. Además, hoy se puede cambiar la fecha de un evento publicado sin que ventas se entere.
- **El event owner no tiene pantallas.** El frontend solo cubre al cliente. Crear, armar y publicar un evento únicamente se puede hacer llamando a la API.

Este change completa el dominio de eventos antes de que las etapas II y III lo necesiten.

## What Changes

- **Clasificación del evento**: tipo (lista fija: `recital`, `teatro`, `deporte`, `conferencia`, `festival`, `otro`), organizador (la productora, que no es lo mismo que el owner), participantes (artistas, equipos u oradores) y descripción. Organizadores y participantes son entidades propias de eventos, creadas al vuelo por nombre y sin duplicados. **BREAKING**: `POST /eventos` exige `tipo` y `organizador`.
- **Edición restringida**: `PATCH /eventos/{id}` edita solo datos descriptivos (nombre, descripción, tipo, organizador, participantes), mientras el evento esté en borrador o publicado y no haya terminado. **BREAKING**: deja de aceptar `fecha`. El recinto queda fijo una vez publicado: si cambia el lugar, el owner cancela el evento.
- **Ciclo de vida**: se guardan los estados `borrador`, `publicado` y `cancelado`. El estado `finalizado` se calcula: un evento publicado cuya fecha de inicio ya llegó.
- **Reprogramación**: un endpoint propio cambia la fecha. En borrador se aplica directo. En un evento publicado se aplica recién cuando ventas confirma la nueva fecha.
- **Cancelación**: se puede cancelar un borrador o un evento publicado. Es un estado final. En un evento publicado, ventas deja de vender.
- **Borrado**: solo se puede borrar un borrador.
- **Sincronización confiable con ventas**: la reprogramación y la cancelación de un evento publicado primero guardan la intención (outbox) y después intentan avisar a ventas. Si ventas no responde, un proceso periódico (`eventos-cron`) reintenta hasta lograrlo. Cada cambio lleva una versión creciente por evento, así ventas tolera reintentos y mensajes desordenados.
- **Ventas conoce la fecha y el estado del evento**: recibe la fecha de inicio con el inventario y las actualizaciones de fecha y cancelación. Rechaza reservas y pagos de eventos cancelados o ya iniciados, sin consultar a eventos.
- **Cartelera con filtros** por tipo y por rango de fechas. Solo lista eventos publicados que todavía no empezaron.
- **Frontend del event owner**: mis eventos, crear y editar un evento, armar sectores y zonas, publicar, reprogramar, cancelar y borrar.

## Capabilities

### New Capabilities

- `eventos/ciclo-de-vida`: estados del evento (guardados y calculados), borrado, cancelación y reprogramación, y la sincronización confiable de esos cambios con ventas.

### Modified Capabilities

- `eventos/catalogo-zonas`: el evento suma tipo, organizador, participantes y descripción; la edición se restringe a datos descriptivos; la publicación entrega también la fecha de inicio; la cartelera agrega filtros y excluye los eventos cancelados y finalizados.
- `ventas/compra-concurrencia`: el inventario recibe la fecha de inicio; ventas acepta actualizaciones versionadas de fecha y cancelación, y cierra la venta de eventos cancelados o iniciados.
- `infraestructura/docker-compose`: nuevo contenedor `eventos-cron` con la imagen de eventos, interno y sin puertos publicados.

## Impact

- **eventos**: tablas nuevas `organizadores`, `participantes`, `evento_participantes` y `outbox`; columnas nuevas en `eventos` (`tipo`, `descripcion`, `organizador_id`, `version`) y el estado `cancelado`. Todo con migración Alembic. Endpoints nuevos: reprogramar, cancelar y borrar. Nuevo proceso `eventos-cron`.
- **ventas**: código de otro integrante, con un cambio acotado y coordinado. Columnas nuevas en `inventario_eventos` (`fecha_inicio`, `cancelado`, `version`) con migración, un endpoint interno de actualización y una validación nueva al reservar y pagar. `fecha_inicio` acepta nulos: los inventarios ya existentes siguen vendiendo como hoy.
- **Comunicación entre servicios**: sigue siendo sync por HTTP de eventos a ventas, pero ahora la reprogramación y la cancelación son eventualmente consistentes mediante el outbox. Ventas no consulta nunca a eventos.
- **gateway**: sin cambios. Las rutas nuevas son protegidas, y las consultas siguen bajo `GET /api/eventos`, que ya es pública.
- **frontend**: pantallas nuevas del owner. Reutiliza la protección de rutas por rol que agrega el change de auth (`feature/auth-cuentas-y-perfil`) cuando esté en `dev`.
- **infraestructura**: un contenedor más en `docker-compose.yml`.
- **Fuera de alcance**: devoluciones y aviso a los compradores ante una cancelación o reprogramación (Etapa III), búsqueda avanzada con relevancia (Etapa III), migrar la publicación al outbox, cambiar el recinto de un evento publicado, e imagen del evento (si hay tiempo, va en un change propio).
