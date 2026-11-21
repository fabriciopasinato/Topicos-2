# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
