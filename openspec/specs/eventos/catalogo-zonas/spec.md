# eventos/catalogo-zonas Specification

## Purpose

Permitir que los event owners definan qué se vende (eventos, recintos, sectores, zonas numeradas o generales y sus precios) y lo publiquen, y que cualquiera consulte la cartelera de eventos publicados.

## Requirements

### Requirement: Gestión de eventos por su owner
Un usuario `event owner` SHALL poder crear eventos y SHALL poder modificar solo los eventos de los que es dueño. Un `administrador` SHALL poder gestionar cualquier evento.

#### Scenario: Owner crea un evento
- **WHEN** un event owner crea un evento con nombre, fecha y recinto
- **THEN** el evento se crea en estado `borrador` con ese usuario como dueño

#### Scenario: Owner edita un evento ajeno
- **WHEN** un event owner intenta modificar un evento cuyo dueño es otro usuario
- **THEN** se responde 403 y el evento no cambia

#### Scenario: Cliente intenta crear un evento
- **WHEN** un usuario con rol `cliente` intenta crear un evento
- **THEN** se responde 403

### Requirement: Definición de zonas numeradas y generales
Un evento SHALL tener sectores con zonas de dos tipos: numeradas (filas y asientos identificados) o generales (capacidad total sin numeración), cada una con su precio.

#### Scenario: Zona numerada
- **WHEN** el owner define una zona numerada con filas A a C y asientos 1 a 10
- **THEN** la zona queda con 30 asientos identificados por fila y número, y su precio

#### Scenario: Zona general
- **WHEN** el owner define una zona general con capacidad 500
- **THEN** la zona queda con capacidad 500 y su precio

#### Scenario: Zona inválida
- **WHEN** el owner define una zona con capacidad 0, sin asientos o con precio negativo
- **THEN** se responde 422 y la zona no se crea

### Requirement: Publicación con entrega de inventario a ventas
Al publicar un evento, el servicio SHALL enviar a `ventas` sus zonas, asientos y precios, y SHALL marcar el evento como `publicado` solo si `ventas` confirma la recepción.

#### Scenario: Publicación exitosa
- **WHEN** el owner publica un evento en borrador con al menos una zona
- **THEN** ventas recibe el inventario y el evento queda en estado `publicado`

#### Scenario: Ventas caído al publicar
- **GIVEN** que el servicio `ventas` no responde
- **WHEN** el owner publica un evento
- **THEN** se responde un error 503, el evento queda en `borrador` y el owner puede reintentar

#### Scenario: Reintento de publicación
- **GIVEN** que ventas ya recibió el inventario de un evento pero la publicación no se completó
- **WHEN** el owner vuelve a publicar
- **THEN** el evento queda `publicado` y ventas no duplica el inventario

#### Scenario: Publicación sin zonas
- **WHEN** el owner intenta publicar un evento sin zonas
- **THEN** se responde 422 y el evento sigue en `borrador`

### Requirement: Zonas inmutables tras la publicación
Una vez publicado, las zonas, asientos y precios de un evento SHALL NOT modificarse.

#### Scenario: Edición de zona publicada
- **WHEN** el owner intenta modificar o borrar una zona de un evento publicado
- **THEN** se responde 409 y la zona no cambia

### Requirement: Consulta pública de la cartelera
Cualquier usuario, autenticado o no, SHALL poder listar y ver el detalle de los eventos publicados con sus zonas y precios. Los eventos en borrador SHALL ser visibles solo para su owner y los administradores.

#### Scenario: Listado público
- **WHEN** un visitante sin token consulta la cartelera
- **THEN** recibe solo los eventos publicados

#### Scenario: Borrador ajeno
- **WHEN** un cliente pide el detalle de un evento en borrador
- **THEN** se responde 404

### Requirement: Eventos no informa disponibilidad
El servicio de eventos SHALL NOT exponer ni calcular la disponibilidad de tickets; esa información pertenece a ventas.

#### Scenario: Detalle de evento
- **WHEN** se consulta el detalle de un evento publicado en eventos
- **THEN** la respuesta incluye zonas, asientos y precios, pero no qué está vendido
