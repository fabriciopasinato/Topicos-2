# Spec Delta: Usuarios y roles

## Purpose

Gestionar la identidad de los usuarios, sus credenciales y sus roles (administrador, event owner, cliente), emitiendo los tokens que el resto del sistema usa para autorizar operaciones.

## ADDED Requirements

### Requirement: Registro público de clientes
El servicio SHALL permitir el registro público con email y contraseña, y SHALL asignar siempre el rol `cliente`, ignorando cualquier rol enviado en la solicitud.

#### Scenario: Registro exitoso
- **WHEN** se envía un registro con email nuevo y contraseña válida
- **THEN** se crea el usuario con rol `cliente` y se responde 201 sin incluir la contraseña

#### Scenario: Intento de registrarse como administrador
- **WHEN** se envía un registro con el campo `rol: administrador` en el cuerpo
- **THEN** el usuario se crea con rol `cliente`

#### Scenario: Email duplicado
- **WHEN** se intenta registrar un email que ya existe
- **THEN** se responde 409 y no se crea otro usuario

#### Scenario: Registro concurrente del mismo email
- **WHEN** llegan al mismo tiempo dos registros con el mismo email
- **THEN** se crea un solo usuario y la otra solicitud recibe 409

### Requirement: Almacenamiento seguro de contraseñas
Las contraseñas SHALL guardarse solo como hash con un algoritmo lento y con sal, y SHALL NOT aparecer en respuestas ni en logs.

#### Scenario: Contraseña en la base
- **WHEN** se registra un usuario
- **THEN** la base guarda un hash distinto de la contraseña en texto plano

### Requirement: Login con emisión de tokens
El servicio SHALL validar las credenciales y, si son correctas, emitir un token de acceso JWT con identificador de usuario, rol y expiración, junto con un refresh token.

#### Scenario: Login exitoso
- **WHEN** un usuario envía email y contraseña correctos
- **THEN** recibe un token de acceso con `sub`, `rol` y `exp`, y un refresh token

#### Scenario: Contraseña incorrecta
- **WHEN** se envía una contraseña que no coincide
- **THEN** se responde 401 con el mismo mensaje que para un email inexistente

#### Scenario: Email inexistente
- **WHEN** se intenta loguear con un email que no existe
- **THEN** se responde 401 sin revelar que el usuario no existe

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
