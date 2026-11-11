# Spec Delta: Gateway, rate limit y bitácora

## MODIFIED Requirements

### Requirement: Validación local del token de acceso
El gateway SHALL validar la firma y la expiración del JWT de acceso con el secreto compartido, sin consultar a `auth` ni guardar sesiones, y SHALL rechazar los tokens emitidos antes de la marca de revocación del usuario publicada en Redis.

#### Scenario: Token válido
- **WHEN** llega una solicitud con un JWT de acceso válido en `Authorization: Bearer`
- **THEN** el gateway reenvía la solicitud agregando `X-User-Id` y `X-User-Role` tomados del token

#### Scenario: Token expirado o con firma inválida
- **WHEN** llega una solicitud a una ruta protegida con un JWT expirado o adulterado
- **THEN** el gateway responde 401 sin llamar al microservicio

#### Scenario: Ruta pública sin token
- **WHEN** llega una solicitud sin token a una ruta pública (login, registro, refresh, verificación de email, reenvío de verificación, olvidé y restablecer contraseña, consulta de cartelera)
- **THEN** el gateway la reenvía sin headers de identidad

#### Scenario: Auth caído
- **GIVEN** que el servicio `auth` está detenido
- **WHEN** llega una solicitud a `eventos` con un JWT válido
- **THEN** la solicitud se procesa normalmente

#### Scenario: Token emitido antes de la revocación
- **GIVEN** que el usuario 7 tiene una marca de revocación de las 10:30
- **WHEN** llega una solicitud con un token del usuario 7 emitido a las 10:00
- **THEN** el gateway responde 401 sin llamar al microservicio

#### Scenario: Token emitido después de la revocación
- **GIVEN** que el usuario 7 tiene una marca de revocación de las 10:30
- **WHEN** llega una solicitud con un token del usuario 7 emitido a las 10:45
- **THEN** la solicitud se procesa normalmente

#### Scenario: Redis no disponible al verificar la revocación
- **GIVEN** que Redis no responde
- **WHEN** llega una solicitud con un token válido
- **THEN** la solicitud se procesa (fail-open) y la falla queda registrada en el log

## ADDED Requirements

### Requirement: Límite estricto en rutas de recuperación de cuenta
Las rutas de verificación de email, reenvío de verificación, olvidé contraseña y restablecer contraseña SHALL pertenecer al grupo de rate limit `auth`, con el mismo límite estricto que login y registro.

#### Scenario: Abuso del pedido de restablecimiento
- **WHEN** una IP supera el límite del grupo auth con pedidos de "olvidé mi contraseña"
- **THEN** el gateway responde 429 con `Retry-After` antes de llamar a `auth`

#### Scenario: Grupo compartido con el login
- **GIVEN** que una IP agotó el límite del grupo auth con intentos de login
- **WHEN** esa IP pide un restablecimiento de contraseña
- **THEN** el gateway responde 429
