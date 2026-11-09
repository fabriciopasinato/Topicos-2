# ventas/compra-concurrencia Specification

## Purpose

Ser la única fuente de verdad sobre qué tickets están disponibles, reservados y vendidos, y procesar reservas y pagos garantizando que un ticket nunca se venda dos veces, incluso con solicitudes simultáneas, reintentos o reservas vencidas.

## Requirements

### Requirement: Recepción del inventario de un evento
Ventas SHALL recibir por un endpoint interno el inventario de un evento publicado y crear un ticket disponible por cada entrada: uno por asiento en las zonas numeradas y uno por unidad de capacidad en las zonas generales, cada uno con una copia del precio. La recepción SHALL ser idempotente por evento.

#### Scenario: Inventario nuevo
- **WHEN** eventos envía el inventario de un evento con una zona numerada de 30 asientos y una general de 500
- **THEN** ventas tiene 30 tickets numerados y 500 tickets generales disponibles para ese evento

#### Scenario: Inventario reenviado
- **WHEN** eventos reenvía el inventario de un evento que ventas ya tiene
- **THEN** ventas responde éxito sin crear tickets duplicados

#### Scenario: Endpoint interno inaccesible desde afuera
- **WHEN** un cliente intenta llamar al endpoint interno de inventario a través del gateway
- **THEN** el gateway no lo expone y responde 404

### Requirement: Consulta de disponibilidad
Ventas SHALL informar, para un evento publicado, qué asientos numerados están disponibles y cuántos tickets quedan en cada zona general. Un ticket con reserva vigente o vendido SHALL figurar como no disponible; un ticket con reserva vencida SHALL figurar como disponible.

#### Scenario: Disponibilidad tras una venta
- **GIVEN** que el asiento A-5 fue vendido
- **WHEN** se consulta la disponibilidad del evento
- **THEN** A-5 figura como no disponible y el resto de la fila como disponible

#### Scenario: Asiento con reserva vigente
- **GIVEN** que el asiento A-6 tiene una reserva que vence dentro de 3 minutos
- **WHEN** se consulta la disponibilidad
- **THEN** A-6 figura como no disponible

#### Scenario: Asiento con reserva vencida
- **GIVEN** que la reserva del asiento A-6 venció hace 1 minuto sin pago
- **WHEN** se consulta la disponibilidad
- **THEN** A-6 figura como disponible

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
Solo un usuario autenticado con rol `cliente` SHALL poder reservar, pagar y cancelar, y cada reserva y orden SHALL quedar asociada a ese usuario.

#### Scenario: Reserva sin autenticación
- **WHEN** se intenta reservar sin token
- **THEN** el gateway responde 401

#### Scenario: Historial propio
- **WHEN** un cliente consulta sus compras
- **THEN** recibe solo sus órdenes pagadas con los tickets y precios pagados
