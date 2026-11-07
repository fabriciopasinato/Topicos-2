# Spec Delta: Gateway, Rate Limit y Bitácora

## Purpose
Proveer un punto de entrada stateless al sistema que aplica autenticación JWT, rate limit distribuido con Redis y bitácora de auditoría persistida.

## ADDED Requirements

### Requirement: Registro obligatorio de bitácora en base de datos
El Gateway DEBE registrar cada solicitud HTTP entrante en la base `gateway_db`, incluyendo métricas temporales y resultado.

#### Scenario: Registro exitoso de petición
- **WHEN** un cliente realiza una solicitud HTTP a cualquier endpoint del Gateway
- **THEN** el Gateway cronometra la duración total, captura el código de estado y persiste el registro en la bitácora antes de finalizar.

#### Scenario: Registro de petición rechazada
- **WHEN** una solicitud es rechazada por error de autenticación o rate limit
- **THEN** la solicitud se registra igualmente en la bitácora con su respectivo código de error (401 o 429).

### Requirement: Control de tasa de peticiones (Rate Limit) por IP
El Gateway DEBE limitar la cantidad de peticiones por IP usando Redis como almacén compartido de contadores.

#### Scenario: Superación del umbral general de peticiones
- **WHEN** una misma IP supera las 100 peticiones por minuto
- **THEN** el Gateway responde inmediatamente con código HTTP 429 Too Many Requests y el header `Retry-After`.

#### Scenario: Umbral estricto en rutas sensibles
- **WHEN** una IP supera el límite estricto definido para endpoints de login o compra de tickets
- **THEN** el Gateway bloquea peticiones subsiguientes respondiendo con 429 antes de invocar a los microservicios internos.

### Requirement: Propagación de identidad y estado stateless
El Gateway DEBE validar tokens JWT sin persistir estado de sesión en memoria y propagar la identidad a los servicios internos.

#### Scenario: Propagación de usuario autenticado
- **WHEN** un cliente envía un token JWT válido en el header Authorization
- **THEN** el Gateway valida la firma e inyecta los headers `X-User-Id` y `X-User-Role` en la petición reenviada al microservicio de destino.

