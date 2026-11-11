# Spec Delta: Usuarios y roles

## MODIFIED Requirements

### Requirement: Registro público de clientes
El servicio SHALL permitir el registro público con email, contraseña, nombre, apellido, DNI, fecha de nacimiento, teléfono y dirección (calle, número, piso/depto opcional, localidad, provincia y código postal). SHALL asignar siempre el rol `cliente`, ignorando cualquier rol enviado, y la cuenta SHALL quedar en estado `pendiente_verificacion` hasta verificar el email.

#### Scenario: Registro exitoso
- **WHEN** se envía un registro con email nuevo, contraseña válida y todos los datos obligatorios
- **THEN** se crea el usuario con rol `cliente` en estado `pendiente_verificacion`, se responde 201 sin incluir la contraseña y se envía un email de verificación

#### Scenario: Intento de registrarse como administrador
- **WHEN** se envía un registro con el campo `rol: administrador` en el cuerpo
- **THEN** el usuario se crea con rol `cliente`

#### Scenario: Email duplicado
- **WHEN** se intenta registrar un email que ya existe
- **THEN** se responde 409 y no se crea otro usuario

#### Scenario: DNI duplicado
- **WHEN** se intenta registrar un DNI que ya pertenece a otra cuenta
- **THEN** se responde 409 y no se crea otro usuario

#### Scenario: Registro concurrente del mismo email
- **WHEN** llegan al mismo tiempo dos registros con el mismo email
- **THEN** se crea un solo usuario y la otra solicitud recibe 409

#### Scenario: Datos obligatorios faltantes o inválidos
- **WHEN** se envía un registro sin dirección, con un DNI que no son 7 u 8 dígitos, con una provincia que no existe o con una fecha de nacimiento futura
- **THEN** se responde 422 indicando los campos inválidos y no se crea el usuario

### Requirement: Almacenamiento seguro de contraseñas
Las contraseñas SHALL guardarse solo como hash con un algoritmo lento y con sal, y SHALL NOT aparecer en respuestas, en logs ni en emails.

#### Scenario: Contraseña en la base
- **WHEN** se registra un usuario
- **THEN** la base guarda un hash distinto de la contraseña en texto plano

#### Scenario: Ningún email contiene contraseñas
- **WHEN** se envía cualquier email de la cuenta (verificación, bloqueo o restablecimiento)
- **THEN** el email contiene un link de un solo uso y nunca una contraseña

### Requirement: Login con emisión de tokens
El servicio SHALL validar las credenciales y, solo si son correctas y la cuenta está `activa`, emitir un token de acceso JWT con identificador, rol, fecha de emisión y expiración, junto con un refresh token, y registrar el momento del login. Con contraseña correcta y cuenta no activa SHALL responder 403 con un código que indique el motivo.

#### Scenario: Login exitoso
- **WHEN** un usuario con cuenta activa envía email y contraseña correctos
- **THEN** recibe un token de acceso con `sub`, `rol`, `iat` y `exp`, y un refresh token, y su `last_login_at` se actualiza

#### Scenario: Contraseña incorrecta
- **WHEN** se envía una contraseña que no coincide
- **THEN** se responde 401 con el mismo mensaje y código que para un email inexistente

#### Scenario: Email inexistente
- **WHEN** se intenta loguear con un email que no existe
- **THEN** se responde 401 sin revelar que el usuario no existe

#### Scenario: Cuenta sin verificar con contraseña correcta
- **WHEN** un usuario en `pendiente_verificacion` envía email y contraseña correctos
- **THEN** se responde 403 con código `email_no_verificado` y no se emiten tokens

#### Scenario: Cuenta bloqueada con contraseña correcta
- **WHEN** un usuario con cuenta `bloqueada` envía email y contraseña correctos
- **THEN** se responde 403 con código `cuenta_bloqueada` y no se emiten tokens

#### Scenario: Cuenta bloqueada con contraseña incorrecta
- **WHEN** se intenta loguear en una cuenta `bloqueada` con una contraseña incorrecta
- **THEN** se responde el mismo 401 genérico que para cualquier credencial inválida, sin revelar el estado

## ADDED Requirements

### Requirement: Política de contraseñas
Toda contraseña nueva (registro, cambio o restablecimiento) SHALL tener entre 10 y 128 caracteres y SHALL ser rechazada si figura en la lista de contraseñas comunes o si es igual al email, sin distinguir mayúsculas. No SHALL exigirse una composición de caracteres determinada.

#### Scenario: Contraseña corta
- **WHEN** se elige una contraseña de 9 caracteres
- **THEN** se responde 422 indicando la longitud mínima

#### Scenario: Contraseña demasiado larga
- **WHEN** se elige una contraseña de 129 caracteres
- **THEN** se responde 422 indicando la longitud máxima

#### Scenario: Contraseña común
- **WHEN** se elige `password123` o `1234567890`
- **THEN** se responde 422 indicando que es una contraseña demasiado común

#### Scenario: Contraseña igual al email
- **WHEN** el usuario `Ana@Example.com` elige `ana@example.com` como contraseña
- **THEN** se responde 422

#### Scenario: Contraseña válida sin símbolos
- **WHEN** se elige una frase de 20 letras minúsculas que no es común
- **THEN** la contraseña es aceptada

### Requirement: Verificación del email
La cuenta `pendiente_verificacion` SHALL pasar a `activa` al presentar el token de verificación enviado por email, válido por 24 horas y de un solo uso. SHALL poder pedirse un reenvío, que responde siempre igual exista o no la cuenta.

#### Scenario: Verificación exitosa
- **WHEN** el usuario presenta un token de verificación vigente
- **THEN** su cuenta queda `activa` y puede loguearse

#### Scenario: Token de verificación vencido o usado
- **WHEN** se presenta un token de verificación vencido o ya usado
- **THEN** se responde 400 y la cuenta no cambia

#### Scenario: Reenvío de verificación
- **WHEN** se pide el reenvío para un email en `pendiente_verificacion`
- **THEN** se envía un email nuevo, el token anterior deja de servir y se responde 202

#### Scenario: Reenvío para email inexistente
- **WHEN** se pide el reenvío para un email que no existe o ya está verificado
- **THEN** se responde el mismo 202 y no se envía ningún email

### Requirement: Bloqueo por intentos fallidos
Al 5º intento consecutivo de login con contraseña incorrecta sobre una cuenta activa, la cuenta SHALL pasar a `bloqueada`, SHALL revocarse todas sus sesiones y SHALL enviarse un email con un link de restablecimiento. Un login exitoso SHALL reiniciar el contador.

#### Scenario: Quinto intento fallido
- **GIVEN** una cuenta activa con 4 intentos fallidos consecutivos
- **WHEN** se envía otra contraseña incorrecta
- **THEN** la cuenta queda `bloqueada`, sus refresh tokens dejan de servir, sus tokens de acceso son rechazados y se envía un único email de restablecimiento

#### Scenario: Login exitoso reinicia el contador
- **GIVEN** una cuenta activa con 3 intentos fallidos
- **WHEN** el usuario se loguea con la contraseña correcta
- **THEN** el contador vuelve a 0

#### Scenario: Intentos fallidos concurrentes
- **GIVEN** una cuenta activa con 3 intentos fallidos
- **WHEN** llegan al mismo tiempo 4 logins con contraseña incorrecta
- **THEN** la cuenta queda `bloqueada` y se envía exactamente un email de bloqueo

### Requirement: Recuperación de contraseña
Cualquier persona SHALL poder pedir el restablecimiento de la contraseña de un email; si la cuenta existe se envía un link de un solo uso válido por 30 minutos, y la respuesta SHALL ser la misma exista o no. Presentar el token con una contraseña nueva válida SHALL fijarla, dejar la cuenta `activa` y verificada, reiniciar el contador y revocar todas las sesiones.

#### Scenario: Pedido de restablecimiento
- **WHEN** se pide el restablecimiento para un email registrado
- **THEN** se responde 202 y se envía un email con el link

#### Scenario: Pedido para email inexistente
- **WHEN** se pide el restablecimiento para un email que no existe
- **THEN** se responde el mismo 202 y no se envía ningún email

#### Scenario: Restablecimiento exitoso desbloquea la cuenta
- **GIVEN** una cuenta `bloqueada` por intentos fallidos
- **WHEN** el usuario presenta el token vigente y una contraseña nueva válida
- **THEN** la contraseña cambia, la cuenta queda `activa` con el contador en 0 y puede loguearse con la nueva

#### Scenario: Restablecimiento verifica el email
- **GIVEN** una cuenta en `pendiente_verificacion`
- **WHEN** completa un restablecimiento de contraseña
- **THEN** la cuenta queda `activa`

#### Scenario: Token de restablecimiento vencido o reutilizado
- **WHEN** se presenta un token de restablecimiento vencido o ya usado
- **THEN** se responde 400 y la contraseña no cambia

#### Scenario: Solo el último pedido sirve
- **WHEN** se pide el restablecimiento dos veces y se usa el token del primer pedido
- **THEN** se responde 400

#### Scenario: Uso concurrente del mismo token
- **WHEN** llegan al mismo tiempo dos restablecimientos con el mismo token
- **THEN** solo uno cambia la contraseña y el otro recibe 400

### Requirement: Perfil del usuario
Todo usuario autenticado SHALL poder ver sus datos y editar nombre, apellido, fecha de nacimiento, teléfono y dirección. Email, DNI, rol y estado SHALL NOT poder modificarse desde el perfil.

#### Scenario: Ver mi perfil
- **WHEN** un usuario autenticado consulta su perfil
- **THEN** recibe sus datos personales, dirección, rol, `created_at`, `updated_at` y `last_login_at`, sin el hash de la contraseña

#### Scenario: Editar mi dirección
- **WHEN** el usuario cambia su localidad y código postal
- **THEN** los datos se guardan y `updated_at` se actualiza

#### Scenario: Intento de cambiar email, DNI o rol
- **WHEN** el usuario envía `rol`, `email` o `dni` en la edición
- **THEN** esos campos se ignoran y no cambian

### Requirement: Cambio de contraseña
Todo usuario autenticado SHALL poder cambiar su contraseña indicando la actual. El cambio SHALL revocar todas sus sesiones anteriores y entregar un par de tokens nuevo para la sesión actual.

#### Scenario: Cambio exitoso
- **WHEN** el usuario envía su contraseña actual correcta y una nueva válida
- **THEN** la contraseña cambia, recibe tokens nuevos y sus tokens anteriores dejan de servir

#### Scenario: Contraseña actual incorrecta
- **WHEN** el usuario envía una contraseña actual incorrecta
- **THEN** se responde 401 y la contraseña no cambia

#### Scenario: Nueva contraseña inválida
- **WHEN** la contraseña nueva no cumple la política
- **THEN** se responde 422 y la contraseña no cambia

### Requirement: Administración de cuentas
Un `administrador` SHALL poder listar las cuentas con búsqueda por email, apellido o DNI y filtros por rol y estado, de forma paginada, y ver el detalle de una cuenta. Otros roles SHALL recibir 403.

#### Scenario: Búsqueda paginada
- **GIVEN** 30 cuentas, 3 de ellas con apellido "Pérez"
- **WHEN** el admin busca "pérez" con tamaño de página 20
- **THEN** recibe esas 3 cuentas y el total de resultados

#### Scenario: Detalle de una cuenta
- **WHEN** el admin consulta una cuenta
- **THEN** recibe sus datos, estado, intentos fallidos, `created_at`, `updated_at` y `last_login_at`, sin el hash de la contraseña

#### Scenario: Cliente intenta listar cuentas
- **WHEN** un `cliente` o `event owner` intenta listar cuentas
- **THEN** se responde 403

### Requirement: Restablecimiento de contraseña por el administrador
Un `administrador` SHALL poder restablecer la contraseña de un usuario puntual. La cuenta SHALL pasar a `bloqueada`, SHALL revocarse sus sesiones y el usuario SHALL recibir un email para crear una contraseña nueva. El administrador SHALL NOT ver ni definir la contraseña.

#### Scenario: Admin restablece una cuenta
- **WHEN** el admin restablece la contraseña de un usuario activo
- **THEN** la contraseña anterior deja de servir, sus sesiones se cortan, recibe el email de restablecimiento y la respuesta no contiene ninguna contraseña

#### Scenario: Login posterior con la contraseña vieja
- **GIVEN** que el admin restableció la cuenta
- **WHEN** el usuario intenta loguearse con su contraseña anterior
- **THEN** se responde 403 con código `cuenta_bloqueada` y debe usar el link del email

### Requirement: Revocación inmediata de sesiones
Al cambiar o restablecer la contraseña y al bloquearse una cuenta, el servicio SHALL invalidar todos los refresh tokens del usuario y SHALL publicar en Redis el instante de revocación, para que los tokens de acceso emitidos antes sean rechazados sin esperar su vencimiento.

#### Scenario: Revocación al bloquear
- **WHEN** una cuenta se bloquea
- **THEN** existe en Redis la marca de revocación del usuario con el instante del bloqueo y sus refresh tokens dejan de servir

#### Scenario: Redis no disponible al revocar
- **GIVEN** que Redis no responde
- **WHEN** una cuenta se bloquea
- **THEN** el bloqueo y la revocación de refresh tokens se completan igual y la falla queda registrada en el log

### Requirement: Auditoría de la cuenta
Cada cuenta SHALL registrar cuándo se creó (`created_at`), cuándo cambió por última vez cualquiera de sus datos (`updated_at`, mantenido por la base ante cualquier modificación) y su último login con contraseña (`last_login_at`).

#### Scenario: Creación
- **WHEN** se crea una cuenta
- **THEN** `created_at` y `updated_at` tienen el instante de creación y `last_login_at` está vacío

#### Scenario: Cualquier modificación actualiza updated_at
- **WHEN** cambia cualquier dato de la cuenta (perfil, estado, contraseña o contador de intentos), incluso por una actualización directa en SQL
- **THEN** `updated_at` pasa a ser el instante de esa modificación

#### Scenario: Renovar el token no cuenta como login
- **WHEN** el usuario renueva su token con el refresh token
- **THEN** `last_login_at` no cambia
