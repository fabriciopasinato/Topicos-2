# Spec Delta: Catálogo y Zonas de Eventos

## Purpose
Permitir a los organizadores publicar eventos y definir sectores con localidades numeradas o generales para su posterior comercialización.

## ADDED Requirements

### Requirement: Definición de sectores y tipos de localidad
El servicio de eventos DEBE permitir estructurar sectores con localidades numeradas o por cupo general.

#### Scenario: Creación de zona con asientos numerados
- **WHEN** un event owner define una zona con distribución de filas y números de asiento
- **THEN** el sistema persiste la estructura para permitir la selección de asientos específicos.

#### Scenario: Creación de zona general
- **WHEN** un event owner define una zona sin numeración con una capacidad máxima total
- **THEN** el sistema registra el cupo disponible asociado al evento.

### Requirement: Consulta de disponibilidad síncrona
El servicio de eventos DEBE responder consultas internas del servicio de ventas para validar existencia y aforo.

#### Scenario: Validación interna para compra
- **WHEN** el servicio de ventas consulta por un evento y zona específicos
- **THEN** el servicio de eventos retorna el estado del evento, tipo de zona y capacidad configurada.

