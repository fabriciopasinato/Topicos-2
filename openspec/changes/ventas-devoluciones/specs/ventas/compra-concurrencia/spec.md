# ventas/compra-concurrencia Specification Delta

## MODIFIED Requirements

### Requirement: Consulta de disponibilidad
Ventas SHALL informar, para un evento publicado, qué asientos numerados están disponibles y cuántos tickets quedan en cada zona general. Un ticket con reserva vigente o vendido SHALL figurar como no disponible; un ticket con reserva vencida o liberado por una devolución aprobada SHALL figurar como disponible.

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

#### Scenario: Ticket liberado por devolución aprobada
- **GIVEN** que el asiento A-5 y una entrada general fueron vendidos y luego devueltos con aprobación de un administrador
- **WHEN** se consulta la disponibilidad del evento
- **THEN** A-5 figura como disponible y la zona general incrementa en 1 su cantidad disponible

### Requirement: Operaciones solo para clientes autenticados
Solo un usuario autenticado con rol `cliente` SHALL poder reservar, pagar y cancelar, y cada reserva y orden SHALL quedar asociada a ese usuario. Al consultar su historial propio, el cliente SHALL recibir todas sus órdenes pagadas con los tickets comprados, su modalidad, el precio pagado y el estado de la última devolución asociada a cada ítem (si existe), manteniendo el registro histórico incluso cuando el ticket haya sido devuelto.

#### Scenario: Reserva sin autenticación
- **WHEN** se intenta reservar sin token
- **THEN** el gateway responde 401

#### Scenario: Historial propio
- **WHEN** un cliente consulta sus compras
- **THEN** recibe solo sus órdenes pagadas con los tickets, su `orden_item_id`, `tipo_zona`, precios pagados y el estado de devolución de cada ticket (o `null` si nunca solicitó devolución)

#### Scenario: Historial conserva tickets devueltos
- **GIVEN** que una orden incluye un ticket cuya devolución fue aprobada
- **WHEN** el cliente consulta sus compras
- **THEN** la orden sigue mostrando ese ticket con su devolución en estado `aprobada`
