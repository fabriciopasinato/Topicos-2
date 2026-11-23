# ventas/compra-concurrencia Specification

## Purpose

Ser la única fuente de verdad sobre qué tickets están disponibles, reservados y vendidos, y procesar reservas y pagos garantizando que un ticket nunca se venda dos veces, incluso con solicitudes simultáneas, reintentos o reservas vencidas.

## Requirements

### Requirement: Recepción del inventario de un evento
Ventas SHALL recibir por un endpoint interno el inventario de un evento publicado, con su fecha de inicio, y crear un ticket disponible por cada entrada: uno por asiento en las zonas numeradas y uno por unidad de capacidad en las zonas generales, cada uno con una copia del precio. La recepción SHALL ser idempotente por evento.

#### Scenario: Inventario nuevo
- **WHEN** eventos envía el inventario de un evento con una zona numerada de 30 asientos y una general de 500
- **THEN** ventas tiene 30 tickets numerados y 500 tickets generales disponibles para ese evento

#### Scenario: Inventario con fecha de inicio
- **WHEN** eventos envía el inventario de un evento que empieza el 20/12 a las 21:00
- **THEN** ventas guarda esa fecha de inicio para el evento

#### Scenario: Inventario reenviado
- **WHEN** eventos reenvía el inventario de un evento que ventas ya tiene
- **THEN** ventas responde éxito sin crear tickets duplicados

#### Scenario: Endpoint interno inaccesible desde afuera
- **WHEN** un cliente intenta llamar al endpoint interno de inventario a través del gateway
- **THEN** el gateway no lo expone y responde 404

### Requirement: Consulta de disponibilidad
Ventas SHALL informar, para un evento publicado, si el evento está `a_la_venta` (`false` si está cancelado o su fecha de inicio ya llegó; `true` en caso contrario), qué asientos numerados están disponibles y cuántos tickets quedan en cada zona general. Un ticket con reserva vigente o vendido SHALL figurar como no disponible; un ticket con reserva vencida o liberado por una devolución aprobada SHALL figurar como disponible.

#### Scenario: Disponibilidad tras una venta
- **GIVEN** que el asiento A-5 fue vendido
- **WHEN** se consulta la disponibilidad del evento
- **THEN** `a_la_venta` es `true`, A-5 figura como no disponible y el resto de la fila como disponible

#### Scenario: Asiento con reserva vigente
- **GIVEN** que el asiento A-6 tiene una reserva que vence dentro de 3 minutos
- **WHEN** se consulta la disponibilidad
- **THEN** A-6 figura como no disponible

#### Scenario: Asiento con reserva vencida
- **GIVEN** que la reserva del asiento A-6 venció hace 1 minuto sin pago
- **WHEN** se consulta la disponibilidad
- **THEN** A-6 figura como disponible

#### Scenario: Ticket liberado por devolución aprobada
- **GIVEN** que el asiento A-5 y una entrada general fueron vendidos y luego devueltos con aprobación de un administrador
- **WHEN** se consulta la disponibilidad del evento
- **THEN** A-5 figura como disponible y la zona general incrementa en 1 su cantidad disponible

#### Scenario: Evento cancelado o iniciado en disponibilidad
- **GIVEN** un evento marcado como `cancelado` o cuya `fecha_inicio` ya pasó
- **WHEN** se consulta la disponibilidad del evento
- **THEN** la respuesta informa `a_la_venta: false` junto con las zonas del inventario

### Requirement: Operaciones independientes del servicio de eventos
Reservar, pagar y cancelar SHALL resolverse solo con los datos de ventas, sin consultar al servicio de eventos.

#### Scenario: Eventos caído
- **GIVEN** que el servicio `eventos` está detenido
- **WHEN** un cliente reserva un asiento disponible y luego paga la reserva
- **THEN** ambas operaciones se completan y la orden usa el precio guardado en ventas

### Requirement: Reserva de asientos numerados sin doble asignación
Una reserva SHALL poder incluir uno o varios asientos numerados de un evento y SHALL ser todo o nada: si algún asiento no está disponible, no se reserva ninguno. Un asiento con reserva vigente o vendido SHALL NOT poder reservarse.

#### Scenario: Reserva exitosa de varios asientos
- **WHEN** un cliente reserva los asientos A-1 y A-2 disponibles
- **THEN** se crea la reserva con 201, con su fecha de vencimiento, y ambos asientos quedan bloqueados para ese cliente

#### Scenario: Un asiento no disponible
- **WHEN** un cliente reserva A-1 y A-2 y A-2 ya está reservado por otro o vendido
- **THEN** se responde 409 indicando A-2 y A-1 sigue disponible

#### Scenario: Reserva concurrente del mismo asiento
- **WHEN** dos clientes reservan el asiento B-7 al mismo tiempo
- **THEN** exactamente una reserva recibe 201, la otra recibe 409 y B-7 queda bloqueado una sola vez

#### Scenario: Reservas concurrentes cruzadas
- **WHEN** un cliente reserva A-1 y A-2 mientras otro reserva A-2 y A-1 al mismo tiempo
- **THEN** exactamente una reserva se completa, la otra recibe 409 y ninguna queda bloqueada esperando

#### Scenario: El rechazo no espera
- **WHEN** un cliente intenta reservar un asiento que otra reserva en curso está tomando
- **THEN** recibe la respuesta sin quedar esperando por tiempo indefinido

### Requirement: Reserva en zonas generales sin sobreventa
Una reserva en zona general SHALL bloquear la cantidad pedida de tickets disponibles de esa zona y SHALL rechazarse completa si no hay suficientes.

#### Scenario: Disponibles suficientes
- **WHEN** un cliente reserva 3 entradas de una zona con 10 disponibles
- **THEN** se crea la reserva con 201 y quedan 7 disponibles

#### Scenario: Disponibles insuficientes
- **WHEN** un cliente pide 5 entradas de una zona con 3 disponibles
- **THEN** se responde 409 y siguen 3 disponibles

#### Scenario: Últimas entradas con reservas concurrentes
- **GIVEN** una zona general con 5 tickets disponibles
- **WHEN** 20 clientes reservan 1 entrada cada uno al mismo tiempo
- **THEN** exactamente 5 reservas reciben 201, 15 reciben 409 y no queda ningún ticket asignado a más de una reserva

### Requirement: Límite de tickets por reserva
Una reserva SHALL NOT superar la cantidad máxima de tickets configurada por variable de entorno, que por defecto es 10.

#### Scenario: Reserva que supera el máximo
- **WHEN** un cliente intenta reservar 11 tickets con el máximo por defecto
- **THEN** se responde 422 y no se reserva ningún ticket

### Requirement: Vencimiento automático de la reserva
Una reserva SHALL bloquear sus tickets durante 5 minutos (configurable por variable de entorno) o hasta que se pague, lo que ocurra primero. Al vencer sin pago, sus tickets SHALL volver a estar disponibles sin intervención manual.

#### Scenario: Reserva vencida liberada
- **GIVEN** que un cliente reservó el asiento C-3 y no pagó
- **WHEN** pasan 5 minutos desde la reserva
- **THEN** C-3 figura como disponible y otro cliente puede reservarlo

#### Scenario: Reserva vigente bloquea
- **GIVEN** que un cliente reservó el asiento C-3 hace 2 minutos
- **WHEN** otro cliente intenta reservar C-3
- **THEN** recibe 409

#### Scenario: Duración configurada
- **WHEN** la duración de reserva está configurada en 10 minutos y un cliente reserva
- **THEN** la reserva vence 10 minutos después de creada

#### Scenario: Liberación tras reinicio del servicio
- **GIVEN** que ventas se reinició mientras había reservas vigentes
- **WHEN** esas reservas alcanzan su vencimiento
- **THEN** sus tickets vuelven a estar disponibles igual que si no hubiera habido reinicio

### Requirement: Pago de la reserva
El dueño de una reserva vigente SHALL poder pagarla. El pago SHALL ser simulado y siempre aprobado; SHALL crear la orden y dejar los tickets vendidos en forma definitiva. Una reserva vencida SHALL NOT poder pagarse.

#### Scenario: Pago en término
- **GIVEN** una reserva vigente de A-1 y A-2
- **WHEN** su dueño la paga
- **THEN** se crea la orden con 201 y A-1 y A-2 quedan vendidos

#### Scenario: Pago de reserva vencida
- **GIVEN** una reserva que venció sin pago
- **WHEN** su dueño intenta pagarla
- **THEN** se responde 409 indicando que la reserva venció y no se crea ninguna orden

#### Scenario: Pago repetido
- **GIVEN** una reserva ya pagada
- **WHEN** su dueño vuelve a pagarla
- **THEN** recibe la misma orden y no se crea otra

#### Scenario: Pago de reserva ajena
- **WHEN** un cliente intenta pagar una reserva de otro usuario
- **THEN** se responde 404

#### Scenario: Pago y nueva reserva en el momento del vencimiento
- **GIVEN** una reserva de B-2 que vence en este instante
- **WHEN** su dueño la paga al mismo tiempo que otro cliente reserva B-2
- **THEN** exactamente una de las dos operaciones tiene éxito y B-2 nunca queda vendido a uno y reservado por otro

### Requirement: Cancelación de la reserva
El dueño de una reserva vigente SHALL poder cancelarla, y sus tickets SHALL volver a estar disponibles de inmediato.

#### Scenario: Cancelación
- **GIVEN** una reserva vigente de A-1
- **WHEN** su dueño la cancela
- **THEN** A-1 figura como disponible al instante

#### Scenario: Cancelación de reserva pagada
- **WHEN** el dueño intenta cancelar una reserva ya pagada
- **THEN** se responde 409 y los tickets siguen vendidos

### Requirement: Idempotencia de la creación de reservas
Crear una reserva SHALL requerir el header `Idempotency-Key`. Una clave ya usada por el mismo usuario con el mismo contenido SHALL devolver la reserva original sin bloquear tickets adicionales.

#### Scenario: Reserva sin clave
- **WHEN** un cliente envía una reserva sin `Idempotency-Key`
- **THEN** se responde 400 y no se reserva nada

#### Scenario: Reintento con la misma clave
- **GIVEN** que una reserva con clave K ya se creó
- **WHEN** el mismo usuario reenvía la misma reserva con la clave K
- **THEN** recibe la misma reserva y no se bloquea ningún ticket adicional

#### Scenario: Reintentos simultáneos con la misma clave
- **WHEN** el mismo usuario envía dos veces la misma reserva con la clave K al mismo tiempo
- **THEN** se crea una sola reserva y ambas respuestas refieren a ella

#### Scenario: Misma clave con otro contenido
- **WHEN** el usuario reutiliza la clave K para una reserva distinta
- **THEN** se responde 422 y no se reserva nada

#### Scenario: Misma clave de usuarios distintos
- **WHEN** dos usuarios distintos usan la misma clave K
- **THEN** cada uno obtiene su propia reserva

#### Scenario: Reserva rechazada reintentada
- **GIVEN** que una reserva con clave K fue rechazada con 409
- **WHEN** el usuario la reintenta con la clave K
- **THEN** la reserva se evalúa de nuevo contra la disponibilidad actual

### Requirement: Operaciones solo para clientes autenticados
Solo un usuario autenticado con rol `cliente` SHALL poder reservar, pagar y cancelar, y cada reserva y orden SHALL quedar asociada a ese usuario. Su historial de compras y el detalle de reservas pagadas SHALL conservar sus tickets y precios pagados aun tras devoluciones aprobadas o reventas, incluyendo modalidad, estado local del evento (`evento_fecha_inicio`, `evento_cancelado`, `evento_estado`) y última devolución de cada ítem.

#### Scenario: Reserva sin autenticación
- **WHEN** se intenta reservar sin token
- **THEN** el gateway responde 401

#### Scenario: Historial propio
- **WHEN** un cliente consulta sus compras
- **THEN** recibe solo sus órdenes pagadas con los tickets, su `orden_item_id`, `tipo_zona`, precios pagados, `evento_fecha_inicio`, `evento_cancelado`, `evento_estado` y el estado de devolución de cada ticket (o `null` si nunca solicitó devolución)

#### Scenario: Historial conserva tickets devueltos
- **GIVEN** que una orden incluye un ticket cuya devolución fue aprobada
- **WHEN** el cliente consulta sus compras
- **THEN** la orden sigue mostrando ese ticket con su devolución en estado `aprobada`

#### Scenario: Historial refleja cancelación o reprogramación del evento
- **GIVEN** que un evento de una orden pagada fue cancelado o reprogramado en `ventas`
- **WHEN** el cliente consulta sus compras
- **THEN** el ticket refleja la `evento_fecha_inicio` actualizada, `evento_cancelado` y `evento_estado` (`cancelado`, `finalizado` o `activo`) sin consultar al servicio `eventos`

#### Scenario: Reserva pagada conserva tickets y total tras devolución aprobada
- **GIVEN** una reserva pagada de A-1 y A-2 con total 3000
- **WHEN** un administrador aprueba la devolución de A-1 (o de ambos asientos, incluso tras una reventa) y el cliente consulta la reserva
- **THEN** la reserva sigue figurando `pagada` con ambos tickets y total 3000

### Requirement: Actualización versionada del evento
Ventas SHALL recibir por un endpoint interno los cambios de fecha de inicio y la cancelación de un evento, cada uno con un número de versión. SHALL aplicar un cambio solo si su versión es mayor a la última aplicada para ese evento, y SHALL responder éxito también cuando lo ignora. Una cancelación aplicada SHALL NOT revertirse.

#### Scenario: Cambio de fecha
- **GIVEN** un evento con fecha de inicio 20/12 y versión 1
- **WHEN** eventos envía la fecha 27/12 con versión 2
- **THEN** ventas responde éxito y el evento queda con fecha 27/12 y versión 2

#### Scenario: Cambio reenviado
- **GIVEN** que ventas ya aplicó la versión 2 de un evento
- **WHEN** eventos reenvía la versión 2
- **THEN** ventas responde éxito y no cambia nada

#### Scenario: Cambio desactualizado
- **GIVEN** que ventas ya aplicó la versión 3 de un evento, con fecha 03/01
- **WHEN** llega tarde la versión 2, con fecha 27/12
- **THEN** ventas responde éxito y el evento sigue con fecha 03/01

#### Scenario: Cambio de fecha posterior a una cancelación
- **GIVEN** que ventas aplicó la cancelación de un evento con versión 3
- **WHEN** llega una reprogramación con versión 4
- **THEN** ventas responde éxito y el evento sigue cancelado

#### Scenario: Evento sin inventario
- **WHEN** eventos envía un cambio para un evento cuyo inventario ventas no tiene
- **THEN** ventas responde 404 y no crea nada

#### Scenario: Endpoint interno inaccesible desde afuera
- **WHEN** un cliente intenta llamar al endpoint interno de actualización a través del gateway
- **THEN** el gateway no lo expone y responde 404

### Requirement: Cierre de la venta de eventos cancelados o iniciados
Ventas SHALL rechazar con 409 las reservas y los pagos de un evento cancelado o cuya fecha de inicio ya llegó, usando solo sus propios datos. Un evento sin fecha de inicio registrada SHALL seguir vendiéndose como antes.

#### Scenario: Reserva de un evento cancelado
- **GIVEN** un evento que ventas tiene como cancelado
- **WHEN** un cliente intenta reservar entradas
- **THEN** se responde 409 y no se reserva nada

#### Scenario: Reserva de un evento iniciado
- **GIVEN** un evento cuya fecha de inicio fue hace 10 minutos
- **WHEN** un cliente intenta reservar entradas
- **THEN** se responde 409 y no se reserva nada

#### Scenario: Pago de una reserva de un evento cancelado
- **GIVEN** una reserva vigente de un evento que luego se canceló
- **WHEN** su dueño intenta pagarla
- **THEN** se responde 409 y no se crea ninguna orden

#### Scenario: Evento sin fecha registrada
- **GIVEN** un evento cuyo inventario se recibió antes de que ventas guardara la fecha de inicio
- **WHEN** un cliente reserva entradas disponibles
- **THEN** la reserva se crea como antes

#### Scenario: Cancelación concurrente con una reserva
- **WHEN** un cliente reserva entradas de un evento al mismo tiempo que ventas aplica su cancelación
- **THEN** o la reserva se rechaza con 409, o se crea antes de la cancelación y su pago posterior se rechaza con 409; en ningún caso se vende una entrada del evento cancelado

#### Scenario: Eventos caído
- **GIVEN** que el servicio `eventos` está detenido y un evento está cancelado en ventas
- **WHEN** un cliente intenta reservar entradas de ese evento
- **THEN** se responde 409 sin consultar a eventos
