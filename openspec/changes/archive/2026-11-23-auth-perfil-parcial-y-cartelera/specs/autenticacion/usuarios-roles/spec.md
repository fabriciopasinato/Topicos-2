# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
