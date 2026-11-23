# Proposal

## Why

La revisión de código del PR de `auth-cuentas-y-perfil` encontró 8 problemas en el módulo de auth. Todos se verificaron contra el código. Varios son bugs que ve el usuario: perfil y administración cierran la sesión en vez de renovar el token, el link de restablecimiento falla si en el navegador quedó una sesión revocada y, a veces, el cambio de contraseña corta la sesión que acaba de abrir. Otros dejan datos inválidos en la base o exponen información en el login. Conviene corregirlos en el mismo PR, antes de que `dev` llegue a `main`.

## What Changes

- **Renovación del token en rutas protegidas de auth** (frontend): el cliente HTTP renueva el token ante un 401 en cualquier ruta protegida, incluidas `/api/auth/perfil`, `/api/auth/admin/*` y `/api/auth/event-owners`. Solo se excluyen las 7 rutas públicas de auth.
- **Sin token en las rutas públicas** (frontend): las rutas públicas de auth (login, registro, refresh, verificación, reenvío, olvidé y restablecer contraseña) se llaman sin `Authorization`. Así un token vencido o revocado que quedó en memoria no hace fallar el restablecimiento.
- **Perfil sin `null` en campos obligatorios**: `PATCH /auth/perfil` responde 422 si un campo obligatorio llega en `null`. Solo `piso_depto` puede vaciarse.
- **Revocación sin cortar la sesión nueva**: al cambiar la contraseña, el instante de revocación se toma antes de emitir los tokens nuevos. Así el token entregado nunca queda con un `iat` anterior a la marca, aunque el commit cruce de segundo.
- **BREAKING (API)**: si la contraseña actual es incorrecta en `POST /auth/perfil/contrasenia`, la respuesta pasa de 401 a **422**, con error en el campo `actual`. El 401 queda reservado para sesión inválida, y el frontend deja de confundirlo con un token vencido.
- **Filtros del listado de cuentas validados**: `rol` y `estado` con un valor inexistente responden 422 en vez de devolver una lista vacía.
- **Búsqueda literal**: en la búsqueda de cuentas, `%` y `_` se buscan como caracteres y no funcionan como comodines.
- **BREAKING (API), login sin oráculo de contraseña**:
  - Una cuenta `bloqueada` recibe siempre el 401 genérico, con la contraseña correcta o no. Deja de existir el 403 `cuenta_bloqueada`; el usuario ya recibió el email con el link de restablecimiento.
  - Una cuenta `pendiente_verificacion` mantiene el 403 `email_no_verificado` con la contraseña correcta. Ahora también cuenta los intentos fallidos y al 5º se bloquea, como una cuenta activa.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `autenticacion/usuarios-roles`:
  - Login: la cuenta bloqueada responde el 401 genérico.
  - Bloqueo por intentos: también aplica a cuentas pendientes de verificación.
  - Perfil: `null` en un campo obligatorio da 422.
  - Cambio de contraseña: 422 con la contraseña actual incorrecta, y la sesión nueva no se revoca.
  - Administración de cuentas: filtros validados y búsqueda literal.
  - Restablecimiento por el administrador: el login posterior responde el 401 genérico.
  - Nuevo requirement con el manejo de la sesión en el frontend: renovación en rutas protegidas de auth y rutas públicas sin token.

## Impact

- **auth**: `app/schemas.py` (PerfilPatch), `app/servicio.py` (login, intento fallido, cambio de contraseña, listado), `app/routers/auth.py` (Ejecutor, cambio de contraseña, filtros del listado), `app/revocacion.py` (documentación del instante).
- **frontend**: `src/api/client.js` (refresh y header `Authorization`), `src/pages/CambiarContrasenia.jsx` (error en `actual` desde el 422), `src/pages/Perfil.jsx` (no envía `null` en campos obligatorios).
- **Tests**:
  - auth: `test_login.py`, `test_bloqueo_y_revocacion.py`, `test_perfil_y_admin.py`.
  - frontend: `client.test.js`, `Login.test.jsx`, `Perfil.test.jsx`.
  - Casos nuevos: token vencido en `/perfil`, link de restablecimiento con la sesión revocada y cambio de contraseña que cruza de segundo.
- **gateway**: sin cambios de código. Sigue rechazando cualquier token inválido que se presente; lo que cambia es que el frontend deja de mandarlo a las rutas públicas.
- **Sin migraciones**: no cambia el esquema.
