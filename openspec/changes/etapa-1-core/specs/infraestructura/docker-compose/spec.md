# Spec Delta: Infraestructura Docker Compose

## Purpose

Proveer el entorno de ejecución completo de la plataforma con un solo comando: contenedores, red interna, bases aisladas por servicio, orden de arranque y persistencia de datos entre ejecuciones.

## ADDED Requirements

### Requirement: Arranque con un solo comando
El sistema SHALL levantarse completo con `docker compose up -d`, creando la red, los volúmenes, las imágenes y los contenedores que falten y reutilizando los que ya existen.

#### Scenario: Primer arranque en una máquina limpia
- **GIVEN** que no existen contenedores, volúmenes ni red del proyecto y existe un `.env` copiado de `.env.example`
- **WHEN** se ejecuta `docker compose up -d`
- **THEN** se crean la red, los volúmenes y todos los contenedores, y todos llegan al estado healthy

#### Scenario: Arranque con contenedores existentes
- **GIVEN** que el entorno ya fue levantado y luego detenido con `docker compose stop`
- **WHEN** se ejecuta `docker compose up -d`
- **THEN** los contenedores existentes se inician sin recrearse y los datos guardados siguen disponibles

### Requirement: Exposición de puertos restringida
Solo los contenedores `frontend` y `gateway` SHALL publicar puertos al host. PostgreSQL, Redis y los microservicios SHALL ser accesibles únicamente desde la red interna de Compose.

#### Scenario: Acceso directo a la base desde el host
- **WHEN** desde el host se intenta conectar a PostgreSQL (5432) o a un microservicio (8001-8003)
- **THEN** la conexión falla porque esos puertos no están publicados

#### Scenario: Comunicación interna por nombre de servicio
- **WHEN** el gateway se conecta a `auth:8001` o un servicio se conecta a `postgres:5432`
- **THEN** la conexión se resuelve por la red interna de Compose

### Requirement: Inicialización de bases solo con volumen vacío
El contenedor PostgreSQL SHALL crear las bases `auth_db`, `eventos_db`, `ventas_db` y `gateway_db` con sus usuarios solo cuando su volumen de datos está vacío. La inicialización SHALL crear únicamente bases, usuarios y permisos, nunca tablas.

#### Scenario: Volumen nuevo
- **GIVEN** que el volumen de PostgreSQL no existe
- **WHEN** se levanta el contenedor `postgres`
- **THEN** existen las 4 bases y los 4 usuarios, y ninguna base tiene tablas creadas por la inicialización

#### Scenario: Volumen existente
- **GIVEN** que el volumen de PostgreSQL ya contiene datos
- **WHEN** se levanta el contenedor `postgres`
- **THEN** la inicialización no se vuelve a ejecutar y los datos existentes se conservan

### Requirement: Aislamiento de credenciales de base por servicio
Cada usuario de base de datos SHALL poder conectarse únicamente a la base de su servicio.

#### Scenario: Usuario accede a su base
- **WHEN** el usuario `auth` se conecta a `auth_db`
- **THEN** la conexión es aceptada

#### Scenario: Usuario intenta acceder a una base ajena
- **WHEN** el usuario `ventas` intenta conectarse a `auth_db`, `eventos_db` o `gateway_db`
- **THEN** PostgreSQL rechaza la conexión por falta de permiso

### Requirement: Esquema aplicado por migraciones al arrancar
Cada servicio con base SHALL aplicar sus migraciones pendientes al arrancar, antes de aceptar requests. El esquema SHALL modificarse solo mediante migraciones.

#### Scenario: Arranque con migraciones pendientes
- **GIVEN** que existe una migración nueva no aplicada en `ventas_db`
- **WHEN** se inicia el contenedor `ventas`
- **THEN** la migración se aplica y luego el servicio empieza a responder

#### Scenario: Arranque sin migraciones pendientes
- **WHEN** se inicia un servicio cuya base ya está al día
- **THEN** el servicio arranca sin modificar el esquema

### Requirement: Orden de arranque por estado de salud
Los contenedores SHALL arrancar en este orden, esperando que la capa anterior esté healthy: `postgres` y `redis`, luego `auth`, `eventos` y `ventas`, luego `gateway`, luego `frontend`. Los microservicios SHALL NOT esperar unos a otros.

#### Scenario: Servicios esperan a la base
- **WHEN** se ejecuta `docker compose up -d` y PostgreSQL todavía no acepta conexiones
- **THEN** `auth`, `eventos` y `ventas` no inician hasta que `postgres` está healthy

#### Scenario: Gateway espera a los servicios
- **WHEN** algún microservicio todavía no está healthy
- **THEN** el gateway no inicia hasta que los tres están healthy y Redis también

#### Scenario: Microservicios independientes entre sí
- **WHEN** `eventos` tarda en arrancar
- **THEN** `ventas` arranca igual, sin esperarlo

### Requirement: Healthchecks que reflejan dependencias
Cada servicio SHALL exponer `GET /health`, que responde 200 solo si sus dependencias están disponibles. El de los microservicios SHALL verificar su base; el del gateway SHALL verificar `gateway_db` y Redis.

#### Scenario: Servicio sano
- **WHEN** se consulta `/health` de `eventos` con su base disponible
- **THEN** responde 200

#### Scenario: Base caída
- **WHEN** se consulta `/health` de `eventos` con PostgreSQL detenido
- **THEN** responde un código de error y Docker marca el contenedor como unhealthy

### Requirement: Recuperación automática
Todos los contenedores SHALL reiniciarse solos ante una caída, y los servicios SHALL recuperar la conexión a la base sin reinicio manual.

#### Scenario: Caída de un microservicio
- **WHEN** el proceso de `ventas` termina inesperadamente
- **THEN** Docker lo reinicia automáticamente

#### Scenario: Reinicio de PostgreSQL con servicios en marcha
- **WHEN** PostgreSQL se reinicia mientras los servicios siguen corriendo
- **THEN** los servicios vuelven a atender requests que usan la base sin ser reiniciados

### Requirement: Configuración por variables de entorno
Toda la configuración (credenciales, secretos, límites, expiraciones) SHALL leerse de variables de entorno. El repositorio SHALL incluir `.env.example` con valores de desarrollo y SHALL NOT incluir `.env`.

#### Scenario: Clon nuevo del repositorio
- **WHEN** alguien clona el repositorio, copia `.env.example` a `.env` y ejecuta `docker compose up -d`
- **THEN** el sistema levanta sin modificar ningún archivo versionado

#### Scenario: Credenciales fuera del código
- **WHEN** se busca en el repositorio una contraseña o secreto real
- **THEN** solo aparecen valores de ejemplo en `.env.example`
