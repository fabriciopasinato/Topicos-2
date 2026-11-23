# ventas/compra-concurrencia Specification Delta

## MODIFIED Requirements

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
