# Propuesta: cuentas, perfil y recuperación en auth

## Why

El módulo de auth de la Etapa I solo registra con email y contraseña, emite tokens y permite al admin crear event owners. Para una ticketera real faltan los datos personales y la dirección del cliente, un perfil que cada usuario pueda ver y editar, la recuperación de contraseña, la protección contra adivinar contraseñas y herramientas para que el administrador gestione cuentas. Además, hoy un cambio de seguridad (bloqueo, restablecimiento) no corta el acceso hasta que vence el token, y no queda registro de cuándo se creó, modificó o usó por última vez una cuenta.

## What Changes

- **Registro ampliado**: nombre, apellido, DNI (único), fecha de nacimiento, teléfono y dirección (calle, número, piso/depto opcional, localidad, provincia, código postal). La cuenta nace en estado `pendiente_verificacion` y se activa con un link enviado por email. **BREAKING**: `POST /auth/registro` exige los campos nuevos.
- **Política de contraseñas**: entre 10 y 128 caracteres, sin reglas de composición forzadas, rechazando contraseñas comunes o iguales al email. Aplica al registro, al cambio y al restablecimiento.
- **Estados de cuenta**: `pendiente_verificacion`, `activa` y `bloqueada`. El login rechaza las cuentas que no están activas y solo revela el motivo si la contraseña es correcta.
- **Bloqueo al 5º intento fallido** de contraseña: la cuenta se bloquea, se cierran sus sesiones y se envía un email para restablecer la contraseña. **BREAKING**: el login puede responder 403 con un código de motivo.
- **Recuperación de contraseña** ("olvidé mi contraseña"): link de un solo uso por email que vence en 30 minutos. El mismo flujo desbloquea la cuenta.
- **Perfil**: cada usuario ve y edita sus datos (salvo email, DNI y rol) y cambia su contraseña indicando la actual.
- **Administración de cuentas**: el admin lista y busca cuentas, ve su detalle y restablece la contraseña de un usuario puntual, lo que bloquea la cuenta y le envía el link para crear una nueva.
- **Revocación inmediata**: cambiar o restablecer la contraseña y el bloqueo invalidan al instante los tokens de acceso ya emitidos (auth registra la revocación en Redis y el gateway la verifica).
- **Auditoría de la cuenta**: `created_at`, `updated_at` (actualizado por la base en cualquier cambio) y `last_login_at`.
- **Email de desarrollo**: un contenedor Mailpit recibe los emails sin entregarlos a nadie. Es interno como el resto de los servicios: no publica puertos y su bandeja se consulta desde la red de Compose.
- **Frontend**: registro con los campos nuevos, verificación de email, olvidé/restablecer contraseña, perfil, cambio de contraseña y panel de administración de cuentas.

## Capabilities

### New Capabilities
_(Ninguna: el change amplía capabilities existentes.)_

### Modified Capabilities
- `autenticacion/usuarios-roles`: registro con datos personales y verificación de email, política de contraseñas, login con estados y bloqueo, recuperación y restablecimiento, perfil, cambio de contraseña, administración de cuentas, revocación y auditoría.
- `seguridad/gateway-rate-limit-bitacora`: rechazo de tokens revocados, nuevas rutas públicas de recuperación de cuenta y su límite estricto de rate limit.
- `infraestructura/docker-compose`: contenedor de email de desarrollo, interno y sin puertos publicados.

## Impact

- **auth**: modelo `users` ampliado, tabla nueva de tokens de cuenta, trigger de `updated_at`, migración Alembic con datos existentes, envío de emails por SMTP, escritura en Redis. Nuevas variables: `REDIS_URL`, `SMTP_*`, `EMAIL_FROM`, `FRONTEND_URL`.
- **gateway**: verificación de revocación en Redis por cada request autenticado; rutas públicas y grupo de rate limit `auth` ampliados. Es el módulo de otro integrante: el cambio es acotado y se coordina.
- **APIs**: `POST /auth/registro` cambia su contrato; nuevos endpoints de verificación, recuperación, perfil y administración bajo `/api/auth/`.
- **Infraestructura**: contenedor `mailpit` solo para desarrollo, sin puertos publicados. Frontend y gateway siguen siendo los únicos accesibles desde fuera de Docker.
- **frontend**: pantallas nuevas y menú según rol.
- Eventos y ventas no cambian.
