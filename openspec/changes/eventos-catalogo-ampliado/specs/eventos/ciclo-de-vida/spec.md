# Spec Delta

## Purpose

Definir los estados por los que pasa un evento (borrador, publicado, cancelado y finalizado), las operaciones que los cambian (borrar, cancelar y reprogramar) y cómo esos cambios llegan a ventas de forma confiable aunque ventas no esté disponible en ese momento.

## ADDED Requirements

### Requirement: Estados del evento
Un evento SHALL estar en uno de estos estados: `borrador`, `publicado` o `cancelado`. Además, un evento publicado cuya fecha de inicio ya llegó SHALL informarse como `finalizado`, calculado al momento de la consulta y sin intervención manual.

#### Scenario: Evento publicado a futuro
- **GIVEN** un evento publicado cuya fecha de inicio es mañana
- **WHEN** se consulta su detalle
- **THEN** su estado es `publicado`

#### Scenario: Evento publicado cuya fecha llegó
- **GIVEN** un evento publicado cuya fecha de inicio fue hace una hora
- **WHEN** se consulta su detalle
- **THEN** su estado es `finalizado`

#### Scenario: Borrador con fecha pasada
- **GIVEN** un borrador cuya fecha de inicio ya pasó
- **WHEN** su owner consulta el detalle
- **THEN** su estado sigue siendo `borrador`

### Requirement: Operaciones del ciclo de vida solo para el owner o un administrador
Borrar, cancelar y reprogramar un evento SHALL estar permitido solo a su owner y a los administradores.

#### Scenario: Owner ajeno
- **WHEN** un event owner intenta cancelar, reprogramar o borrar un evento de otro owner
- **THEN** se responde 403 y el evento no cambia

#### Scenario: Cliente
- **WHEN** un usuario con rol `cliente` intenta cancelar un evento
- **THEN** se responde 403 y el evento no cambia

#### Scenario: Administrador
- **WHEN** un administrador cancela un evento en borrador de cualquier owner
- **THEN** el evento queda `cancelado`

### Requirement: Borrado de borradores
Un evento SHALL poder borrarse solo mientras está en `borrador`. Al borrarse SHALL desaparecer junto con sus sectores, zonas y asientos.

#### Scenario: Borrado de un borrador
- **WHEN** el owner borra un evento en borrador
- **THEN** se responde 204 y el evento deja de existir, también para su owner

#### Scenario: Borrado de un evento publicado o cancelado
- **WHEN** el owner intenta borrar un evento publicado o cancelado
- **THEN** se responde 409 y el evento no cambia

### Requirement: Cancelación de un borrador
Un evento en `borrador` SHALL poder cancelarse de inmediato, sin avisar a ventas porque ventas todavía no tiene su inventario.

#### Scenario: Cancelación de un borrador
- **WHEN** el owner cancela un evento en borrador
- **THEN** se responde 200 y el evento queda `cancelado`

### Requirement: Cancelación de un evento publicado
Cancelar un evento publicado SHALL quedar registrado antes de avisar a ventas. El evento SHALL pasar a `cancelado` solo cuando ventas confirma la cancelación. Si ventas no responde, la cancelación SHALL quedar pendiente y el evento SHALL seguir `publicado` hasta que se confirme.

#### Scenario: Cancelación con ventas disponible
- **WHEN** el owner cancela un evento publicado y ventas confirma
- **THEN** se responde 200, el evento queda `cancelado` y ventas deja de vender sus entradas

#### Scenario: Cancelación con ventas caído
- **GIVEN** que el servicio `ventas` no responde
- **WHEN** el owner cancela un evento publicado
- **THEN** se responde 202, el evento sigue `publicado` y su detalle informa al owner una cancelación pendiente

#### Scenario: Cancelación de un evento finalizado
- **WHEN** el owner intenta cancelar un evento finalizado
- **THEN** se responde 409 y el evento no cambia

#### Scenario: Cancelación repetida
- **WHEN** el owner cancela un evento que ya está `cancelado`
- **THEN** se responde 200 y no se registra una nueva operación

### Requirement: Estado final de la cancelación
Un evento `cancelado` SHALL NOT poder editarse, reprogramarse, publicarse ni borrarse.

#### Scenario: Reprogramar un evento cancelado
- **WHEN** el owner intenta reprogramar un evento cancelado
- **THEN** se responde 409 y el evento no cambia

#### Scenario: Editar un evento cancelado
- **WHEN** el owner intenta editar el nombre de un evento cancelado
- **THEN** se responde 409 y el evento no cambia

### Requirement: Reprogramación de un borrador
La fecha de inicio de un evento en `borrador` SHALL cambiarse mediante la operación de reprogramación, que se aplica de inmediato. La nueva fecha SHALL ser futura.

#### Scenario: Reprogramación de un borrador
- **WHEN** el owner reprograma un borrador para dentro de un mes
- **THEN** se responde 200 y el evento tiene la nueva fecha

#### Scenario: Fecha en el pasado
- **WHEN** el owner reprograma un evento para una fecha que ya pasó
- **THEN** se responde 422 y la fecha no cambia

### Requirement: Reprogramación de un evento publicado
Reprogramar un evento publicado SHALL quedar registrado antes de avisar a ventas. La nueva fecha SHALL aplicarse en eventos solo cuando ventas la confirma. Mientras tanto, el evento SHALL conservar la fecha anterior y la reprogramación SHALL quedar pendiente.

#### Scenario: Reprogramación con ventas disponible
- **WHEN** el owner reprograma un evento publicado y ventas confirma
- **THEN** se responde 200, el evento tiene la nueva fecha y ventas cierra la venta en la nueva fecha

#### Scenario: Reprogramación con ventas caído
- **GIVEN** que el servicio `ventas` no responde
- **WHEN** el owner reprograma un evento publicado
- **THEN** se responde 202, el evento conserva la fecha anterior y su detalle informa al owner la reprogramación pendiente

#### Scenario: Reprogramación de un evento finalizado
- **WHEN** el owner intenta reprogramar un evento finalizado
- **THEN** se responde 409 y la fecha no cambia

### Requirement: Reintento automático de operaciones pendientes
Las cancelaciones y reprogramaciones pendientes SHALL reenviarse a ventas periódicamente, sin intervención del owner, hasta que ventas las confirme. Un reenvío SHALL NOT duplicar el efecto en ventas.

#### Scenario: Ventas vuelve a estar disponible
- **GIVEN** una cancelación pendiente porque ventas estaba caído
- **WHEN** ventas vuelve a responder y transcurre el siguiente ciclo de reintento
- **THEN** ventas recibe la cancelación y el evento queda `cancelado`

#### Scenario: Falla entre la confirmación de ventas y el registro en eventos
- **GIVEN** que ventas aplicó una reprogramación pero eventos se detuvo antes de registrar la confirmación
- **WHEN** eventos vuelve a arrancar y transcurre el siguiente ciclo de reintento
- **THEN** la reprogramación se reenvía, ventas la acepta sin cambiar nada más y el evento queda con la nueva fecha

#### Scenario: Reintento tras un reinicio
- **GIVEN** una reprogramación pendiente
- **WHEN** se reinician los contenedores de eventos
- **THEN** la reprogramación sigue pendiente y se reenvía en el siguiente ciclo

### Requirement: Orden de los cambios de un evento
Cada cancelación o reprogramación de un evento publicado SHALL tener un número de versión mayor al de la anterior. Tanto eventos como ventas SHALL aplicar un cambio solo si su versión es mayor a la última aplicada, de modo que el estado final no dependa del orden en que llegan los mensajes. Una cancelación aplicada SHALL NOT revertirse por ningún cambio posterior.

#### Scenario: Dos reprogramaciones pendientes
- **GIVEN** que con ventas caído el owner reprogramó un evento para el 27/12 y luego para el 03/01
- **WHEN** ventas vuelve y recibe ambas, en cualquier orden
- **THEN** tanto eventos como ventas quedan con la fecha 03/01

#### Scenario: Cancelación después de una reprogramación pendiente
- **GIVEN** una reprogramación pendiente de un evento
- **WHEN** el owner cancela ese evento y luego ambas operaciones llegan a ventas
- **THEN** el evento queda `cancelado` en eventos y en ventas

#### Scenario: Reprogramación y cancelación simultáneas
- **WHEN** el owner envía al mismo tiempo una reprogramación y una cancelación del mismo evento publicado
- **THEN** cada una recibe una versión distinta y el evento termina `cancelado` en eventos y en ventas, sin importar cuál tenga la versión mayor

### Requirement: Cancelación pendiente bloquea cambios nuevos
Mientras un evento tenga una cancelación pendiente, SHALL rechazarse cualquier reprogramación o edición nueva de ese evento.

#### Scenario: Reprogramar con una cancelación pendiente
- **GIVEN** un evento publicado con una cancelación pendiente
- **WHEN** el owner intenta reprogramarlo
- **THEN** se responde 409 y no se registra ninguna operación nueva
