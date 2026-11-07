# Spec Delta: Compra y Concurrencia de Tickets

## Purpose
Procesar compras y reservas de tickets garantizando atomicidad, idempotencia y prevención total de sobreventa bajo alta concurrencia.

## ADDED Requirements

### Requirement: Prevención de doble venta en asientos numerados
El sistema DEBE impedir que un mismo asiento en un evento sea adquirido por más de un comprador simultáneamente.

#### Scenario: Compra concurrente del mismo asiento numerado
- **WHEN** dos compradores intentan reservar el mismo asiento exactamente en el mismo instante
- **THEN** una de las operaciones se procesa exitosamente con código HTTP 201 Created y la otra es rechazada con código HTTP 409 Conflict.

### Requirement: Control atómico de cupos en zonas generales
El sistema DEBE decrementar el cupo disponible de forma atómica impidiendo sobrepasar la capacidad máxima establecida.

#### Scenario: Agotamiento de cupo general
- **WHEN** se solicita la compra de entradas generales cuando el cupo restante es menor a la cantidad solicitada
- **THEN** la transacción falla y retorna código HTTP 409 Conflict indicando cupo agotado.

### Requirement: Idempotencia en órdenes de compra
El sistema DEBE soportar el header `Idempotency-Key` para evitar transacciones duplicadas por reintentos de red.

#### Scenario: Reintento de compra con misma clave de idempotencia
- **WHEN** el cliente reenvía una solicitud de compra con una clave de idempotencia ya procesada
- **THEN** el sistema no procesa un nuevo cobro ni descuenta cupo adicional, y retorna el resultado previamente generado.

