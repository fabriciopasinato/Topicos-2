# Spec Delta

## MODIFIED Requirements

### Requirement: Login con emisión de tokens
El servicio SHALL validar las credenciales y, solo si son correctas y la cuenta está `activa`, emitir un token de acceso JWT con identificador, rol, fecha de emisión y expiración, junto con un refresh token, y registrar el momento del login. Con contraseña correcta y cuenta `pendiente_verificacion` SHALL responder 403 con el código `email_no_verificado`. Una cuenta `bloqueada` SHALL recibir siempre el mismo 401 genérico que una credencial inválida, sea la contraseña correcta o no, para que el login no confirme contraseñas de cuentas bloqueadas.

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

## ADDED Requirements

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
