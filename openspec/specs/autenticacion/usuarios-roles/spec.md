# autenticacion/usuarios-roles Specification

## Purpose

Gestionar la identidad de los usuarios, sus credenciales y sus roles (administrador, event owner, cliente), emitiendo los tokens que el resto del sistema usa para autorizar operaciones.

## Requirements

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
El servicio SHALL validar las credenciales y, solo si son correctas y la cuenta está `activa`, emitir un token de acceso JWT con identificador, rol, fecha de emisión y expiración, junto con un refresh token, y registrar el momento del login. Con contraseña correcta y cuenta `pendiente_verificacion` SHALL responder 403 con el código `email_no_verificado`. Una cuenta `bloqueada` SHALL recibir siempre el mismo 401 genérico que una credencial inválida, sea la contraseña correcta o no.

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
- **THEN** se responde el mismo 401 genérico, con el mismo mensaje y código, que para cualquier credencial inválida, y no se emiten tokens

#### Scenario: Cuenta bloqueada con contraseña incorrecta
- **WHEN** se intenta loguear en una cuenta `bloqueada` con una contraseña incorrecta
- **THEN** se responde el mismo 401 genérico que para cualquier credencial inválida, sin revelar el estado

#### Scenario: Correcta e incorrecta indistinguibles en una cuenta bloqueada
- **GIVEN** una cuenta `bloqueada`
- **WHEN** se intenta el login una vez con la contraseña correcta y otra con una incorrecta
- **THEN** las dos respuestas tienen el mismo status y el mismo cuerpo

### Requirement: Expiración configurable del token de acceso
El token de acceso SHALL expirar a las 2 horas por defecto, con una duración configurable por variable de entorno.

#### Scenario: Expiración por defecto
- **WHEN** se emite un token de acceso sin configuración especial
- **THEN** su `exp` es 2 horas después de su emisión

#### Scenario: Expiración configurada
- **WHEN** la variable de expiración está fijada en 30 minutos y se emite un token
- **THEN** su `exp` es 30 minutos después de su emisión

### Requirement: Renovación del token de acceso
El servicio SHALL permitir obtener un nuevo token de acceso presentando un refresh token vigente. Cada uso SHALL invalidar el refresh token presentado y entregar uno nuevo.

#### Scenario: Refresh exitoso
- **WHEN** un usuario presenta un refresh token vigente
- **THEN** recibe un token de acceso nuevo y un refresh token nuevo

#### Scenario: Refresh token reutilizado
- **WHEN** se presenta un refresh token que ya fue usado
- **THEN** se responde 401 y no se emiten tokens

#### Scenario: Refresh token expirado
- **WHEN** se presenta un refresh token vencido
- **THEN** se responde 401 y el usuario debe volver a loguearse

#### Scenario: Refresh concurrente con el mismo token
- **WHEN** llegan al mismo tiempo dos solicitudes de refresh con el mismo refresh token
- **THEN** solo una obtiene tokens nuevos y la otra recibe 401

#### Scenario: Rol actualizado al renovar
- **GIVEN** que el rol del usuario cambió después del login
- **WHEN** renueva su token de acceso
- **THEN** el nuevo token contiene el rol actual

### Requirement: Alta de event owners por un administrador
Solo un usuario con rol `administrador` SHALL poder crear usuarios con rol `event owner`.

#### Scenario: Administrador crea un event owner
- **WHEN** un administrador crea un usuario event owner
- **THEN** el usuario se crea con rol `event owner`

#### Scenario: Cliente intenta crear un event owner
- **WHEN** un usuario con rol `cliente` o `event owner` intenta crear un event owner
- **THEN** se responde 403 y no se crea el usuario

### Requirement: Administrador inicial idempotente
Al arrancar, el servicio SHALL crear el administrador inicial con las credenciales de las variables de entorno si no existe, y SHALL NOT modificarlo ni duplicarlo si ya existe.

#### Scenario: Primer arranque
- **WHEN** `auth` arranca con la base sin usuarios
- **THEN** existe un usuario administrador con el email configurado

#### Scenario: Arranques siguientes
- **WHEN** `auth` se reinicia y el administrador ya existe
- **THEN** sigue existiendo un solo administrador inicial y su contraseña no cambia

### Requirement: Autorización por rol en los servicios
Cada servicio SHALL autorizar las operaciones según el rol recibido del gateway, respondiendo 403 cuando el rol no tiene permiso.

#### Scenario: Cliente accede a una operación de administración
- **WHEN** un usuario con rol `cliente` intenta una operación reservada al administrador
- **THEN** se responde 403

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
Al 5º intento consecutivo de login con contraseña incorrecta sobre una cuenta `activa` o `pendiente_verificacion`, la cuenta SHALL pasar a `bloqueada`, SHALL revocarse todas sus sesiones y SHALL enviarse un email con un link de restablecimiento. Un login con la contraseña correcta SHALL reiniciar el contador, aunque la cuenta esté pendiente de verificación y no se emitan tokens.

#### Scenario: Quinto intento fallido
- **GIVEN** una cuenta activa con 4 intentos fallidos consecutivos
- **WHEN** se envía otra contraseña incorrecta
- **THEN** la cuenta queda `bloqueada`, sus refresh tokens dejan de servir, sus tokens de acceso son rechazados y se envía un único email de restablecimiento

#### Scenario: Quinto intento fallido en una cuenta sin verificar
- **GIVEN** una cuenta en `pendiente_verificacion` con 4 intentos fallidos consecutivos
- **WHEN** se envía otra contraseña incorrecta
- **THEN** la cuenta queda `bloqueada` y se envía un único email de restablecimiento, cuyo uso deja la cuenta `activa`

#### Scenario: Login exitoso reinicia el contador
- **GIVEN** una cuenta activa con 3 intentos fallidos
- **WHEN** el usuario se loguea con la contraseña correcta
- **THEN** el contador vuelve a 0

#### Scenario: Contraseña correcta en una cuenta sin verificar reinicia el contador
- **GIVEN** una cuenta en `pendiente_verificacion` con 3 intentos fallidos
- **WHEN** el usuario envía la contraseña correcta
- **THEN** se responde 403 `email_no_verificado` y el contador vuelve a 0

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
Todo usuario autenticado SHALL poder ver sus datos y editar nombre, apellido, fecha de nacimiento, teléfono y dirección. Email, DNI, rol y estado SHALL NOT poder modificarse desde el perfil. Los campos obligatorios SHALL NOT poder vaciarse: solo `piso_depto` admite quedar sin valor.

#### Scenario: Ver mi perfil
- **WHEN** un usuario autenticado consulta su perfil
- **THEN** recibe sus datos personales, dirección, rol, `created_at`, `updated_at` y `last_login_at`, sin el hash de la contraseña

#### Scenario: Editar mi dirección
- **WHEN** el usuario cambia su localidad y código postal
- **THEN** los datos se guardan y `updated_at` se actualiza

#### Scenario: Intento de cambiar email, DNI o rol
- **WHEN** el usuario envía `rol`, `email` o `dni` en la edición
- **THEN** esos campos se ignoran y no cambian

#### Scenario: Campo obligatorio en null
- **WHEN** el usuario envía `null` en un campo obligatorio, por ejemplo `{"localidad": null}`
- **THEN** se responde 422 indicando el campo y ningún dato del perfil cambia

#### Scenario: Vaciar el piso o departamento
- **WHEN** el usuario envía `{"piso_depto": null}`
- **THEN** el piso o departamento queda vacío y el resto del perfil no cambia

#### Scenario: Completar un perfil incompleto de a un campo
- **GIVEN** un event owner o un administrador creado sin datos de perfil
- **WHEN** completa solo su teléfono y guarda desde el frontend
- **THEN** el teléfono se guarda y los demás datos siguen vacíos, sin errores por los campos que no tocó

### Requirement: Cambio de contraseña
Todo usuario autenticado SHALL poder cambiar su contraseña indicando la actual. El cambio SHALL revocar todas sus sesiones anteriores y entregar un par de tokens nuevo para la sesión actual, que SHALL ser aceptado por el gateway en cuanto se recibe. Una contraseña actual incorrecta SHALL responder 422 con el error en el campo `actual`, para no confundirse con una sesión inválida (401).

#### Scenario: Cambio exitoso
- **WHEN** el usuario envía su contraseña actual correcta y una nueva válida
- **THEN** la contraseña cambia, recibe tokens nuevos y sus tokens anteriores dejan de servir

#### Scenario: El token nuevo sirve aunque el cambio cruce de segundo
- **GIVEN** que el cambio de contraseña empieza en un segundo y termina en el siguiente
- **WHEN** el usuario usa el token de acceso recibido en la respuesta
- **THEN** el gateway lo acepta y la marca de revocación no es posterior a su `iat`

#### Scenario: Contraseña actual incorrecta
- **WHEN** el usuario envía una contraseña actual incorrecta
- **THEN** se responde 422 con el error asociado al campo `actual`, la contraseña no cambia y la sesión sigue activa

#### Scenario: Nueva contraseña inválida
- **WHEN** la contraseña nueva no cumple la política
- **THEN** se responde 422 y la contraseña no cambia

### Requirement: Administración de cuentas
Un `administrador` SHALL poder listar las cuentas con búsqueda por email, apellido o DNI y filtros por rol y estado, de forma paginada, y ver el detalle de una cuenta. Otros roles SHALL recibir 403. El texto de búsqueda SHALL compararse en forma literal, sin caracteres comodín, y un rol o estado inexistente en los filtros SHALL responder 422.

#### Scenario: Búsqueda paginada
- **GIVEN** 30 cuentas, 3 de ellas con apellido "Pérez"
- **WHEN** el admin busca "pérez" con tamaño de página 20
- **THEN** recibe esas 3 cuentas y el total de resultados

#### Scenario: Búsqueda con caracteres comodín
- **GIVEN** las cuentas `a_b@example.com` y `axb@example.com`
- **WHEN** el admin busca `a_b`
- **THEN** recibe solo `a_b@example.com`, y buscar `%` devuelve solo las cuentas que contienen ese carácter

#### Scenario: Filtro con valor inexistente
- **WHEN** el admin lista cuentas con `rol=superusuario` o `estado=cualquiera`
- **THEN** se responde 422

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
- **THEN** se responde el 401 genérico de credenciales inválidas y debe usar el link del email

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

### Requirement: Sesión del usuario en el frontend
El frontend SHALL renovar el token de acceso con el refresh token ante un 401 en cualquier ruta protegida, incluidas las de auth (perfil, administración y alta de event owners), y reintentar la solicitud una vez. Las rutas públicas de auth SHALL llamarse sin token de acceso, para que una sesión vencida o revocada no impida usarlas. Al completar un restablecimiento de contraseña, el frontend SHALL descartar la sesión guardada, porque el backend revoca todas las sesiones de la cuenta.

#### Scenario: Token vencido en el perfil
- **GIVEN** un usuario con el token de acceso vencido y un refresh token vigente
- **WHEN** abre su perfil
- **THEN** el frontend renueva el token, reintenta la consulta y muestra el perfil sin cerrar la sesión

#### Scenario: Token vencido en la administración
- **GIVEN** un administrador con el token de acceso vencido y un refresh token vigente
- **WHEN** abre el listado de cuentas
- **THEN** el frontend renueva el token y muestra el listado

#### Scenario: Refresh rechazado
- **GIVEN** un usuario cuyo refresh token ya no sirve
- **WHEN** una ruta protegida responde 401
- **THEN** el frontend cierra la sesión y lleva al login con el aviso de sesión cerrada

#### Scenario: Restablecimiento con una sesión revocada en el navegador
- **GIVEN** un navegador que conserva un token de acceso revocado
- **WHEN** el usuario abre el link de restablecimiento y elige una contraseña nueva válida
- **THEN** la solicitud se envía sin token, la contraseña cambia y no se intenta renovar la sesión

#### Scenario: El restablecimiento cierra la sesión guardada
- **GIVEN** un navegador con una sesión guardada
- **WHEN** el usuario completa un restablecimiento de contraseña
- **THEN** la sesión guardada se descarta y el frontend muestra el login sin las opciones de usuario autenticado

#### Scenario: Login con credenciales inválidas
- **WHEN** el login responde 401
- **THEN** el frontend muestra el error de credenciales y no intenta renovar ningún token

### Requirement: Lecturas públicas con la sesión revocada
Si una lectura pública (cartelera, detalle de un evento, tipos, recintos o disponibilidad) responde 401 y la renovación del token también falla, el frontend SHALL descartar la sesión y repetir la lectura sin token, sin redirigir al login. Las rutas que requieren sesión SHALL mantener la redirección al login con el aviso de sesión cerrada.

#### Scenario: Cartelera con la sesión revocada
- **GIVEN** un navegador con una sesión revocada, cuyo refresh token tampoco sirve
- **WHEN** el usuario abre la cartelera
- **THEN** la sesión se descarta, la cartelera se muestra y el encabezado ofrece ingresar

#### Scenario: Detalle de un evento con la sesión revocada
- **GIVEN** un navegador con una sesión revocada
- **WHEN** el usuario abre el detalle de un evento publicado
- **THEN** ve el evento y su disponibilidad sin ser llevado al login

#### Scenario: Mis eventos con la sesión revocada
- **GIVEN** un event owner con la sesión revocada
- **WHEN** abre "Mis eventos"
- **THEN** la sesión se cierra y el frontend lo lleva al login con el aviso de sesión cerrada
