# Spec Delta

## MODIFIED Requirements

### Requirement: Orden de arranque por estado de salud
Los contenedores SHALL arrancar en este orden, esperando que la capa anterior esté healthy: `postgres` y `redis`, luego `auth`, `eventos` y `ventas`, luego `gateway` y `eventos-cron`, luego `frontend`. `eventos-cron` SHALL esperar solo a `eventos`, que es quien aplica las migraciones de su base. Los microservicios SHALL NOT esperar unos a otros.

#### Scenario: Servicios esperan a la base
- **WHEN** se ejecuta `docker compose up -d` y PostgreSQL todavía no acepta conexiones
- **THEN** `auth`, `eventos` y `ventas` no inician hasta que `postgres` está healthy

#### Scenario: Gateway espera a los servicios
- **WHEN** algún microservicio todavía no está healthy
- **THEN** el gateway no inicia hasta que los tres están healthy y Redis también

#### Scenario: Microservicios independientes entre sí
- **WHEN** `eventos` tarda en arrancar
- **THEN** `ventas` arranca igual, sin esperarlo

#### Scenario: El proceso periódico espera las migraciones de eventos
- **WHEN** `eventos` todavía no terminó de aplicar sus migraciones
- **THEN** `eventos-cron` no inicia hasta que `eventos` está healthy

#### Scenario: El proceso periódico no espera a ventas
- **GIVEN** que `ventas` está detenido
- **WHEN** se ejecuta `docker compose up -d`
- **THEN** `eventos-cron` arranca igual y sus reenvíos quedan pendientes hasta que `ventas` responda

## ADDED Requirements

### Requirement: Contenedor del proceso periódico de eventos
El contenedor `eventos-cron` SHALL usar la misma imagen que `eventos`, SHALL conectarse solo a `eventos_db` con las credenciales de eventos, SHALL NOT publicar puertos al host y SHALL reiniciarse solo ante una caída.

#### Scenario: Sin puertos publicados
- **WHEN** se inspeccionan los puertos publicados por `eventos-cron`
- **THEN** no publica ninguno

#### Scenario: Caída del proceso
- **WHEN** el proceso de `eventos-cron` termina inesperadamente
- **THEN** Docker lo reinicia sin intervención manual

#### Scenario: Proceso colgado
- **GIVEN** que `eventos-cron` dejó de completar ciclos de reintento
- **WHEN** Docker ejecuta su healthcheck
- **THEN** el contenedor figura como unhealthy
