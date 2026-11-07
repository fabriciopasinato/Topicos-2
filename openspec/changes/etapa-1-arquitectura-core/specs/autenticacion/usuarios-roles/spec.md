# Spec Delta: Usuarios y Roles

## Purpose
Gestionar la identidad, credenciales seguras y control de acceso basado en roles para administradores, event owners y clientes.

## ADDED Requirements

### Requirement: Registro y autenticación de usuarios
El servicio de autenticación DEBE permitir el registro de usuarios y la emisión de tokens JWT tras validar credenciales con hash seguro.

#### Scenario: Autenticación exitosa
- **WHEN** un usuario envía credenciales válidas a `/login`
- **THEN** el servicio retorna un token JWT firmado que incluye el identificador de usuario y su rol.

#### Scenario: Contraseña incorrecta
- **WHEN** se ingresa una contraseña no coincidente
- **THEN** el servicio rechaza la solicitud con código HTTP 401 Unauthorized sin revelar si el usuario existe.

### Requirement: Control de acceso basado en roles
El sistema DEBE restringir operaciones según los roles `administrador`, `event owner` y `cliente`.

#### Scenario: Event owner crea evento
- **WHEN** un usuario con rol `event owner` intenta crear un nuevo evento
- **THEN** la operación es autorizada.

#### Scenario: Cliente intenta acceder a recursos administrativos
- **WHEN** un usuario con rol `cliente` intenta acceder a una ruta de administración
- **THEN** el sistema rechaza la petición con código HTTP 403 Forbidden.

