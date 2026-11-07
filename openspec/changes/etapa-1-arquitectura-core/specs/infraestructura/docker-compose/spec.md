# Spec Delta: Infraestructura Docker Compose

## Purpose
Proveer el entorno de ejecución orquestado mediante Docker Compose con redes aisladas, persistencia idempotente de volúmenes y supervisión de salud.

## ADDED Requirements

### Requirement: Aislamiento de redes públicas e internas
El sistema DEBE separar el tráfico de red en una red pública accesible por clientes y una red interna aislada para servicios y datos.

#### Scenario: Contenedores internos inaccesibles directamente desde el host
- **WHEN** un cliente externo intenta conectarse directamente al puerto de PostgreSQL (5432) o microservicios (8001-8003) desde el host
- **THEN** la conexión es rechazada por no tener puertos publicados hacia el host.

#### Scenario: Comunicación interna entre servicios
- **WHEN** el API Gateway resuelve el nombre de host `auth` o `postgres`
- **THEN** la red interna `internal_net` permite la comunicación directa sin salir al host.

### Requirement: Idempotencia y persistencia de contenedores
El sistema DEBE mantener los datos de las bases de datos y la configuración de contenedores si estos ya existen, evitando reinicializaciones accidentales.

#### Scenario: Reinicio del entorno sin pérdida de datos
- **WHEN** se ejecuta `docker compose up -d` en un entorno previamente iniciado y detenido
- **THEN** Docker mantiene y reutiliza los contenedores existentes sin recrear los volúmenes de datos ni reejecutar los scripts de inicialización de PostgreSQL.

### Requirement: Supervisión de salud y recuperación automática
Todos los servicios DEBEN implementar verificación de salud (`/health`) y política de reinicio automático.

#### Scenario: Falla de un servicio y recuperación
- **WHEN** un microservicio finaliza de manera inesperada
- **THEN** Docker Compose lo reinicia automáticamente debido a la política `restart: unless-stopped`.

