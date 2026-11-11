# Spec Delta: Infraestructura Docker Compose

## ADDED Requirements

### Requirement: Servidor de email de desarrollo
El entorno SHALL incluir un servidor de email de desarrollo que reciba por SMTP, desde la red interna, todos los emails que envía el sistema y SHALL NOT entregarlos a destinatarios reales. Como el resto de los servicios internos, SHALL NOT publicar puertos al host: su bandeja SHALL consultarse solo desde la red interna de Compose.

#### Scenario: Email enviado por auth
- **WHEN** auth envía un email de verificación a `ana@example.com`
- **THEN** el email queda en la bandeja del servidor de desarrollo y no sale de la máquina

#### Scenario: Sin puertos publicados
- **WHEN** desde el host o desde otra máquina de la red se intenta conectar al SMTP (1025) o a la bandeja web (8025) del servidor de email
- **THEN** la conexión falla porque esos puertos no están publicados

#### Scenario: Lectura de la bandeja desde la red interna
- **WHEN** se consulta la API de la bandeja desde otro contenedor de la red de Compose
- **THEN** se obtienen los emails recibidos con sus links

#### Scenario: Arranque con el resto del entorno
- **WHEN** se ejecuta `docker compose up -d`
- **THEN** el servidor de email arranca junto con los demás contenedores, con healthcheck y reinicio automático

#### Scenario: Cambio a un proveedor real
- **WHEN** se configuran las variables SMTP con los datos de un proveedor externo
- **THEN** auth envía los emails a ese proveedor sin cambios de código
