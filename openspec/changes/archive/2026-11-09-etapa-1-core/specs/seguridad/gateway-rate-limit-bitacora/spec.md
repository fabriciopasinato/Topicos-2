# Spec Delta: Gateway, rate limit y bitácora

## Purpose

Ser el único punto de entrada del frontend: valida la identidad, protege a los microservicios del abuso con rate limit por IP y registra cada solicitud en una bitácora persistente, sin guardar estado propio en memoria.

## ADDED Requirements

### Requirement: Punto de entrada único
El gateway SHALL ser el único componente del backend accesible desde el host y SHALL reenviar cada request al microservicio correspondiente según el prefijo de ruta (`/api/auth`, `/api/eventos`, `/api/ventas`).

#### Scenario: Ruteo a un microservicio
- **WHEN** el frontend envía `GET /api/eventos`
- **THEN** el gateway reenvía la solicitud a `eventos` y devuelve su respuesta al cliente

#### Scenario: Ruta inexistente
- **WHEN** llega una solicitud a un prefijo que no corresponde a ningún servicio
- **THEN** el gateway responde 404 sin llamar a ningún microservicio

### Requirement: Descarte de headers de identidad enviados por el cliente
El gateway SHALL eliminar los headers `X-User-Id` y `X-User-Role` que lleguen en la solicitud del cliente antes de cualquier otro procesamiento.

#### Scenario: Rol falsificado por el cliente
- **WHEN** un cliente envía `X-User-Role: administrador` sin token o con un token de rol `cliente`
- **THEN** el microservicio recibe la identidad que surge del token (o ninguna) y nunca el valor enviado por el cliente

### Requirement: Validación local del token de acceso
El gateway SHALL validar la firma y la expiración del JWT de acceso con el secreto compartido, sin consultar a `auth` ni guardar sesiones.

#### Scenario: Token válido
- **WHEN** llega una solicitud con un JWT de acceso válido en `Authorization: Bearer`
- **THEN** el gateway reenvía la solicitud agregando `X-User-Id` y `X-User-Role` tomados del token

#### Scenario: Token expirado o con firma inválida
- **WHEN** llega una solicitud a una ruta protegida con un JWT expirado o adulterado
- **THEN** el gateway responde 401 sin llamar al microservicio

#### Scenario: Ruta pública sin token
- **WHEN** llega una solicitud sin token a una ruta pública (login, registro, refresh, consulta de cartelera)
- **THEN** el gateway la reenvía sin headers de identidad

#### Scenario: Auth caído
- **GIVEN** que el servicio `auth` está detenido
- **WHEN** llega una solicitud a `eventos` con un JWT válido
- **THEN** la solicitud se procesa normalmente

### Requirement: Rate limit por IP antes de llamar a los servicios
El gateway SHALL limitar las solicitudes por IP y por grupo de rutas usando contadores en Redis, antes de validar el token o llamar a un microservicio. Al superar el límite SHALL responder 429 con `Retry-After` igual a los segundos que faltan para que termine la ventana.

#### Scenario: Límite general superado
- **GIVEN** el límite general por defecto de 100 solicitudes por minuto
- **WHEN** una IP envía la solicitud número 101 a rutas de consulta dentro del mismo minuto
- **THEN** el gateway responde 429 con `Retry-After` y no llama al microservicio

#### Scenario: Límite estricto en login
- **WHEN** una IP supera el límite del grupo auth con solicitudes de login
- **THEN** el gateway responde 429 con `Retry-After` antes de llamar a `auth`

#### Scenario: Límite estricto en registro
- **WHEN** una IP supera el límite del grupo auth con solicitudes de registro
- **THEN** el gateway responde 429 con `Retry-After` antes de llamar a `auth`

#### Scenario: Límite estricto en compra
- **WHEN** una IP supera el límite del grupo compra con solicitudes de reserva, pago o cancelación
- **THEN** el gateway responde 429 con `Retry-After` antes de llamar a `ventas`

#### Scenario: Grupos independientes
- **WHEN** una IP agotó el límite del grupo auth
- **THEN** sus consultas de cartelera siguen respondiéndose mientras no superen el límite general

#### Scenario: Retry-After refleja el tiempo restante
- **WHEN** una IP supera el límite cuando faltan 20 segundos para terminar la ventana
- **THEN** el header `Retry-After` vale 20 o menos, nunca la duración completa de la ventana

#### Scenario: Límites configurables
- **WHEN** se cambian los límites en las variables de entorno y se reinicia el gateway
- **THEN** se aplican los nuevos valores sin cambiar el código

### Requirement: Contadores compartidos entre instancias
Los contadores de rate limit SHALL guardarse en Redis para que todas las instancias del gateway compartan el mismo conteo por IP.

#### Scenario: Dos instancias del gateway
- **GIVEN** dos instancias del gateway conectadas al mismo Redis
- **WHEN** una IP reparte sus solicitudes entre ambas instancias
- **THEN** el límite se aplica sobre el total, no por instancia

### Requirement: Bitácora de todas las solicitudes
El gateway SHALL registrar en `gateway_db`, antes de devolver la respuesta, cada solicitud recibida con IP, método, ruta, usuario (si lo hay), código de respuesta y duración en milisegundos medida desde que se recibió.

#### Scenario: Solicitud exitosa
- **WHEN** un cliente realiza una solicitud que el microservicio responde con 200
- **THEN** existe un registro en la bitácora con su IP, método, ruta, usuario, código 200 y duración

#### Scenario: Solicitud rechazada por rate limit
- **WHEN** una solicitud es rechazada con 429
- **THEN** existe un registro en la bitácora con código 429

#### Scenario: Solicitud rechazada por autenticación
- **WHEN** una solicitud es rechazada con 401
- **THEN** existe un registro en la bitácora con código 401

#### Scenario: Microservicio caído
- **WHEN** el microservicio destino no responde y el gateway devuelve un error 5xx
- **THEN** existe un registro en la bitácora con ese código de error

### Requirement: La bitácora no bloquea el servicio
Si `gateway_db` no está disponible, el gateway SHALL igual responder la solicitud y SHALL emitir el registro fallido por la salida estándar.

#### Scenario: Base de bitácora caída
- **GIVEN** que `gateway_db` no acepta conexiones
- **WHEN** llega una solicitud válida
- **THEN** el cliente recibe la respuesta del microservicio y el registro aparece en los logs del contenedor

### Requirement: Gateway sin estado local
El gateway SHALL NOT guardar sesiones, contadores ni registros en memoria o en archivos del contenedor.

#### Scenario: Reinicio del gateway
- **WHEN** el contenedor del gateway se recrea
- **THEN** los tokens vigentes siguen siendo válidos, los contadores de rate limit se conservan en Redis y la bitácora previa sigue en `gateway_db`
