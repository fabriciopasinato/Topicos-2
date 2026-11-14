# Spec Delta

## MODIFIED Requirements

### Requirement: Gestión de eventos por su owner
Un usuario `event owner` SHALL poder crear eventos indicando nombre, fecha de inicio, recinto, tipo y organizador, y opcionalmente descripción y participantes. SHALL poder modificar solo los eventos de los que es dueño. Un `administrador` SHALL poder gestionar cualquier evento.

#### Scenario: Owner crea un evento
- **WHEN** un event owner crea un evento con nombre, fecha, recinto, tipo `recital`, organizador "DF Entertainment" y participantes "Los Piojos" y "Ciro"
- **THEN** el evento se crea en estado `borrador` con ese usuario como dueño y con esos datos

#### Scenario: Evento sin tipo u organizador
- **WHEN** un event owner crea un evento sin tipo o sin organizador
- **THEN** se responde 422 y el evento no se crea

#### Scenario: Owner edita un evento ajeno
- **WHEN** un event owner intenta modificar un evento cuyo dueño es otro usuario
- **THEN** se responde 403 y el evento no cambia

#### Scenario: Cliente intenta crear un evento
- **WHEN** un usuario con rol `cliente` intenta crear un evento
- **THEN** se responde 403

### Requirement: Publicación con entrega de inventario a ventas
Al publicar un evento, el servicio SHALL enviar a `ventas` sus zonas, asientos, precios y su fecha de inicio, y SHALL marcar el evento como `publicado` solo si `ventas` confirma la recepción. Un evento cuya fecha de inicio ya pasó SHALL NOT poder publicarse.

#### Scenario: Publicación exitosa
- **WHEN** el owner publica un evento en borrador con al menos una zona
- **THEN** ventas recibe el inventario con la fecha de inicio y el evento queda en estado `publicado`

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

#### Scenario: Publicación con fecha pasada
- **GIVEN** un borrador cuya fecha de inicio ya pasó
- **WHEN** el owner intenta publicarlo
- **THEN** se responde 422 y el evento sigue en `borrador`

### Requirement: Consulta pública de la cartelera
Cualquier usuario, autenticado o no, SHALL poder listar los eventos publicados que todavía no empezaron, y ver el detalle de los eventos publicados, finalizados o cancelados después de publicarse, con su clasificación, zonas y precios. Los borradores, y los eventos cancelados sin haberse publicado, SHALL ser visibles solo para su owner y los administradores.

#### Scenario: Listado público
- **WHEN** un visitante sin token consulta la cartelera
- **THEN** recibe solo los eventos publicados cuya fecha de inicio es futura, ordenados por fecha

#### Scenario: Borrador ajeno
- **WHEN** un cliente pide el detalle de un evento en borrador
- **THEN** se responde 404

#### Scenario: Detalle de un evento cancelado
- **GIVEN** un evento que se publicó y luego se canceló
- **WHEN** un visitante pide su detalle
- **THEN** recibe el evento con estado `cancelado`

#### Scenario: Borrador cancelado
- **GIVEN** un evento que se canceló estando en borrador
- **WHEN** un cliente pide su detalle
- **THEN** se responde 404

#### Scenario: Detalle con clasificación
- **WHEN** un visitante pide el detalle de un evento publicado
- **THEN** la respuesta incluye tipo, organizador, participantes, descripción y estado

## ADDED Requirements

### Requirement: Tipo de evento de una lista fija
El tipo de un evento SHALL ser uno de: `recital`, `teatro`, `deporte`, `conferencia`, `festival` u `otro`.

#### Scenario: Tipo válido
- **WHEN** el owner crea un evento de tipo `teatro`
- **THEN** el evento se crea con ese tipo

#### Scenario: Tipo inexistente
- **WHEN** el owner crea o edita un evento con tipo `stand-up`
- **THEN** se responde 422 y el evento no se crea ni cambia

### Requirement: Organizadores y participantes sin duplicados
Organizadores y participantes SHALL identificarse por su nombre, sin distinguir mayúsculas ni espacios sobrantes. Indicar un nombre que ya existe SHALL reutilizarlo y un nombre nuevo SHALL crearlo. Un mismo participante SHALL NOT figurar dos veces en un evento.

#### Scenario: Nombre ya existente
- **GIVEN** que existe el participante "Los Piojos"
- **WHEN** un owner crea otro evento con el participante " los piojos "
- **THEN** ambos eventos quedan asociados al mismo participante "Los Piojos"

#### Scenario: Participante repetido en un evento
- **WHEN** el owner indica "Ciro" dos veces como participante de un evento
- **THEN** el evento queda con "Ciro" una sola vez

#### Scenario: Alta simultánea del mismo nombre
- **WHEN** dos owners crean al mismo tiempo eventos con el organizador nuevo "Fenix"
- **THEN** existe un solo organizador "Fenix" y ambos eventos quedan asociados a él

#### Scenario: Nombre vacío
- **WHEN** el owner indica un organizador o participante vacío
- **THEN** se responde 422 y el evento no se crea ni cambia

### Requirement: Edición de datos descriptivos
La edición de un evento SHALL permitir cambiar nombre, descripción, tipo, organizador y participantes mientras el evento esté en `borrador` o `publicado`. El recinto SHALL poder cambiarse solo en `borrador`. La fecha de inicio SHALL NOT cambiarse por edición, solo por reprogramación.

#### Scenario: Edición de un evento publicado
- **WHEN** el owner cambia la descripción y los participantes de un evento publicado
- **THEN** los cambios se guardan y ventas no recibe ningún aviso

#### Scenario: Fecha en la edición
- **WHEN** el owner envía una fecha en la edición de un evento
- **THEN** se responde 422 indicando que la fecha se cambia por reprogramación, y el evento no cambia

#### Scenario: Recinto de un evento publicado
- **WHEN** el owner intenta cambiar el recinto de un evento publicado
- **THEN** se responde 409 y el evento no cambia

#### Scenario: Edición de un evento finalizado
- **WHEN** el owner intenta editar un evento finalizado
- **THEN** se responde 409 y el evento no cambia

### Requirement: Filtros de la cartelera
La cartelera SHALL poder filtrarse por tipo y por rango de fechas de inicio, combinables entre sí.

#### Scenario: Filtro por tipo
- **WHEN** un visitante consulta la cartelera filtrando por tipo `recital`
- **THEN** recibe solo los recitales publicados que todavía no empezaron

#### Scenario: Filtro por rango de fechas
- **WHEN** un visitante filtra los eventos entre el 1/12 y el 31/12
- **THEN** recibe solo los eventos publicados cuya fecha de inicio cae en ese rango

#### Scenario: Filtro inválido
- **WHEN** un visitante filtra por un tipo inexistente o con un rango cuyo inicio es posterior a su fin
- **THEN** se responde 422
