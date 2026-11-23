# ventas/devoluciones Specification

## Purpose

Permitir que los clientes soliciten la devolución de tickets individuales ya comprados y que los administradores revisen, aprueben o rechacen esas solicitudes, respetando el ciclo de vida del evento (cancelado vs. finalizado), liberando el asiento específico o el cupo de zona general al aprobarse y garantizando consistencia bajo concurrencia.

## ADDED Requirements

### Requirement: Solicitud de devolución de un ticket comprado
Un usuario autenticado con rol `cliente` SHALL poder solicitar la devolución de un ticket individual perteneciente a una orden pagada propia, indicando opcionalmente un motivo. La solicitud SHALL crearse en estado `pendiente` y SHALL NOT liberar el ticket hasta que un administrador la apruebe. Si el evento ya inició y no está cancelado, la solicitud SHALL rechazarse con 409; si el evento está cancelado o no tiene fecha de inicio registrada, SHALL permitirse.

#### Scenario: Solicitud exitosa de ticket numerado
- **GIVEN** que un cliente compró el asiento A-1 en una orden pagada para un evento a futuro
- **WHEN** el cliente solicita la devolución de ese ticket indicando un motivo
- **THEN** se crea la solicitud con 201 en estado `pendiente` y el asiento A-1 sigue figurando como no disponible

#### Scenario: Solicitud exitosa de ticket de zona general
- **GIVEN** que un cliente compró 2 entradas en una zona general y una de ellas tiene `orden_item_id` X
- **WHEN** el cliente solicita la devolución de ese ítem
- **THEN** se crea la solicitud con 201 en estado `pendiente` y el cupo disponible de la zona no cambia todavía

#### Scenario: Solicitud sobre evento ya iniciado no cancelado
- **GIVEN** que un cliente compró un ticket para un evento cuya `fecha_inicio` ya pasó y no fue cancelado
- **WHEN** el cliente intenta solicitar la devolución de ese ítem
- **THEN** se responde 409 y no se crea ninguna solicitud

#### Scenario: Solicitud sobre evento cancelado
- **GIVEN** que un cliente compró un ticket para un evento marcado como `cancelado` en ventas (aun si su fecha original ya pasó)
- **WHEN** el cliente solicita la devolución de ese ítem
- **THEN** se crea la solicitud con 201 en estado `pendiente`

#### Scenario: Solicitud sobre evento sin fecha de inicio registrada
- **GIVEN** que el inventario del evento no tiene `fecha_inicio` registrada y no está cancelado
- **WHEN** el cliente solicita la devolución de un ítem comprado de ese evento
- **THEN** se crea la solicitud con 201 en estado `pendiente`

#### Scenario: Solicitud sobre compra ajena
- **WHEN** un cliente intenta solicitar la devolución de un ticket comprado por otro usuario
- **THEN** se responde 404 y no se crea ninguna solicitud

#### Scenario: Solicitud sobre ticket inexistente o no vendido en esa orden
- **WHEN** un cliente solicita la devolución de un ítem inexistente o de un ítem sin devolución activa cuyo ticket ya no está vendido en esa orden
- **THEN** se responde 404 y no se crea ninguna solicitud

#### Scenario: Solicitud duplicada sobre un ítem con devolución pendiente o aprobada
- **GIVEN** que el ítem ya tiene una solicitud de devolución en estado `pendiente` o `aprobada`
- **WHEN** el cliente intenta crear otra solicitud para el mismo ítem
- **THEN** se responde 409 y no se crea una segunda solicitud

#### Scenario: Nueva solicitud tras un rechazo previo
- **GIVEN** que una solicitud anterior del ítem fue rechazada por un administrador
- **WHEN** el cliente envía una nueva solicitud de devolución para el mismo ítem
- **THEN** se crea la nueva solicitud con 201 en estado `pendiente` conservando el registro histórico de la solicitud rechazada

#### Scenario: Solicitudes concurrentes duplicadas del mismo ítem
- **WHEN** un cliente envía al mismo tiempo dos solicitudes de devolución para el mismo ítem comprado
- **THEN** exactamente una recibe 201, la otra recibe 409 y queda registrada una única solicitud pendiente

#### Scenario: Rol no autorizado para solicitar devolución
- **WHEN** un usuario con rol `administrador` o `event_owner` intenta crear una solicitud de devolución
- **THEN** se responde 403

### Requirement: Consulta de solicitudes de devolución
Un `cliente` SHALL poder consultar únicamente sus propias solicitudes de devolución. Un `administrador` SHALL poder listar todas las solicitudes de devolución, con filtro opcional por estado (`pendiente`, `aprobada`, `rechazada`). Cada solicitud SHALL incluir los datos del ticket y el estado local del evento (`evento_fecha_inicio`, `evento_cancelado`).

#### Scenario: Cliente lista sus devoluciones
- **GIVEN** que existen solicitudes del cliente A y del cliente B
- **WHEN** el cliente A consulta el listado de devoluciones
- **THEN** recibe únicamente las solicitudes del cliente A con los datos del ticket (modalidad, zona, asiento si es numerada, precio, estado) y `evento_fecha_inicio` y `evento_cancelado`

#### Scenario: Administrador filtra solicitudes pendientes
- **GIVEN** que existen solicitudes en estado `pendiente`, `aprobada` y `rechazada`, incluyendo una de un evento cancelado
- **WHEN** un administrador consulta el listado con filtro `estado=pendiente`
- **THEN** recibe únicamente las solicitudes pendientes de todos los clientes informando `evento_cancelado` y `evento_fecha_inicio`

#### Scenario: Event owner intenta consultar devoluciones
- **WHEN** un usuario con rol `event_owner` consulta el listado de devoluciones
- **THEN** se responde 403

### Requirement: Aprobación de devolución y liberación diferenciada por modalidad
Solo un usuario autenticado con rol `administrador` SHALL poder aprobar una solicitud de devolución `pendiente`. Al aprobarse, la solicitud SHALL pasar a `aprobada` registrando quién y cuándo la resolvió, y el ticket SHALL volver atómicamente a `disponible`: en zona `numerada` se libera el asiento específico (`fila`, `numero`) y en zona `general` se incrementa en 1 el cupo disponible.

#### Scenario: Aprobación de devolución de asiento numerado
- **GIVEN** una solicitud pendiente para el asiento A-1 vendido en una orden
- **WHEN** un administrador aprueba la solicitud
- **THEN** la solicitud pasa a `aprobada`, el asiento A-1 figura disponible en la consulta de disponibilidad y otro cliente puede reservarlo y comprarlo

#### Scenario: Aprobación de devolución de entrada en zona general
- **GIVEN** una zona general con 0 disponibles y una solicitud pendiente de devolución de 1 entrada de esa zona
- **WHEN** un administrador aprueba la solicitud
- **THEN** la solicitud pasa a `aprobada`, la zona pasa a tener 1 entrada disponible y otro cliente puede reservarla y comprarla

#### Scenario: Aprobación sobre evento cancelado
- **GIVEN** una solicitud pendiente de un ticket perteneciente a un evento marcado como `cancelado`
- **WHEN** un administrador aprueba la solicitud
- **THEN** la solicitud pasa a `aprobada` y el evento continúa rechazando nuevas reservas con 409

#### Scenario: Aprobación de solicitud presentada antes del inicio del evento
- **GIVEN** una solicitud creada en término antes de la `fecha_inicio` del evento, cuando el evento ya comenzó
- **WHEN** un administrador aprueba la solicitud
- **THEN** la solicitud pasa a `aprobada` sin error

#### Scenario: Reventa y nueva devolución de un ticket liberado
- **GIVEN** que el asiento A-1 fue devuelto por el cliente A (aprobada) y luego comprado por el cliente B en una nueva orden
- **WHEN** el cliente B solicita la devolución de A-1 y un administrador la aprueba
- **THEN** se crea y aprueba la nueva devolución sin conflicto con la devolución histórica del cliente A y A-1 vuelve a quedar disponible

#### Scenario: Aprobación por rol no administrador
- **WHEN** un cliente o event owner intenta aprobar una solicitud de devolución
- **THEN** se responde 403

#### Scenario: Aprobación de solicitud ya resuelta
- **GIVEN** una solicitud ya `aprobada` o `rechazada`
- **WHEN** un administrador intenta aprobarla
- **THEN** se responde 409 y el estado no cambia

### Requirement: Rechazo de devolución por administrador
Solo un usuario autenticado con rol `administrador` SHALL poder rechazar una solicitud de devolución en estado `pendiente`, pudiendo incluir una nota o motivo de resolución. Al rechazarse, la solicitud SHALL pasar a estado `rechazada` y el ticket SHALL permanecer vendido al cliente.

#### Scenario: Rechazo exitoso
- **GIVEN** una solicitud pendiente para el asiento B-2
- **WHEN** un administrador la rechaza indicando un motivo
- **THEN** la solicitud pasa a `rechazada` con la nota registrada y el asiento B-2 sigue vendido y no disponible

#### Scenario: Rechazo de solicitud ya resuelta
- **GIVEN** una solicitud ya `aprobada` o `rechazada`
- **WHEN** un administrador intenta rechazarla
- **THEN** se responde 409

### Requirement: Resolución concurrente de devoluciones
La aprobación y el rechazo de una solicitud de devolución SHALL ejecutarse mediante actualización condicional atómica para evitar resoluciones duplicadas o contradictorias bajo concurrencia.

#### Scenario: Dos administradores resuelven la misma solicitud simultáneamente
- **GIVEN** una solicitud de devolución en estado `pendiente`
- **WHEN** un administrador intenta aprobarla al mismo tiempo que otro intenta aprobarla o rechazarla
- **THEN** exactamente una operación tiene éxito (200), la otra recibe 409 y el ticket queda en un estado consistente con la operación ganadora

### Requirement: Operaciones de devolución independientes de eventos
Solicitar, listar, aprobar y rechazar devoluciones SHALL resolverse únicamente con los datos de `ventas`, sin consultar al servicio `eventos`.

#### Scenario: Servicio de eventos detenido durante una devolución
- **GIVEN** que el servicio `eventos` está detenido
- **WHEN** un cliente solicita una devolución y un administrador la aprueba
- **THEN** ambas operaciones se completan y el ticket vuelve a estar disponible en ventas
