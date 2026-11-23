# Tasks

## 1. Login sin oráculo y bloqueo de cuentas pendientes (punto 6)

- [x] 1.1 En `servicio.login()`, aplicar el orden del design (decisión 4): bloqueada con contraseña correcta → `CredencialesInvalidas`; pendiente con contraseña correcta → reiniciar `intentos_fallidos` y `CuentaNoActiva("email_no_verificado")`. En el router, quitar el mensaje de `cuenta_bloqueada`. Verificar: en `test_login.py`, la cuenta bloqueada con contraseña correcta e incorrecta da el mismo status y el mismo cuerpo 401.
- [x] 1.2 En `_registrar_intento_fallido()`, admitir `estado IN ('activa', 'pendiente_verificacion')` en el UPDATE atómico. Verificar con tests: una cuenta pendiente con 4 fallos queda `bloqueada` al 5º y recibe un solo email; la contraseña correcta en una pendiente con 3 fallos responde 403 `email_no_verificado` y deja el contador en 0; con el link del email la cuenta queda `activa`.
- [x] 1.3 Actualizar los tests que esperaban 403 `cuenta_bloqueada` (`test_login.py`, `test_bloqueo_y_revocacion.py`, `test_perfil_y_admin.py`, el login posterior al restablecimiento del admin) para que esperen el 401 genérico. Verificar: `python -m pytest services/auth` en verde.
- [x] 1.4 En el frontend, ajustar `Login.test.jsx`: el caso de `cuenta_bloqueada` pasa a ser un 401 que muestra "Email o contraseña incorrectos.". Verificar: `npm test` en verde.

## 2. Revocación sin cortar la sesión nueva (punto 4)

- [x] 2.1 Cambiar `Efectos.revocaciones` a una lista de `(user_id, instante | None)`, actualizar `_bloquear_sesiones()` y hacer que `Ejecutor.aplicar()` pase el instante a `revocacion.publicar()`. Verificar: los tests existentes de bloqueo y revocación siguen en verde.
- [x] 2.2 En `cambiar_contrasenia()`, tomar `instante = int(time.time())` antes de `_emitir_tokens()` y anotarlo con la revocación. Actualizar el docstring de `revocacion.py`. Verificar con un test que simula el cruce de segundo (el reloj de `publicar` adelantado): la marca en Redis es igual al instante tomado, es `<=` que el `iat` del token nuevo, y ese token pasa la regla del gateway (`iat >= marca`).

## 3. Perfil sin null en campos obligatorios (punto 3)

- [x] 3.1 Agregar a `PerfilPatch` el validador que rechaza `None` en los campos enviados, salvo `piso_depto`. Verificar con tests: `{"localidad": null}` responde 422 con `loc` en `localidad` y el perfil no cambia; `{"piso_depto": null}` lo vacía.
- [x] 3.2 En `Perfil.jsx`, convertir `""` en `null` solo para `piso_depto`. Verificar en `Perfil.test.jsx`: vaciar el piso envía `null` y un 422 del backend se muestra junto al campo.

## 4. Cambio de contraseña con 422 en `actual` (punto 5)

- [x] 4.1 En el router, convertir `CredencialesInvalidas` de `cambiar_contrasenia` en `_error_campo("actual", ...)`. Verificar con un test: la contraseña actual incorrecta responde 422 con `loc` `["body", "actual"]`, la contraseña no cambia y el token de la sesión sigue sirviendo.
- [x] 4.2 En `CambiarContrasenia.jsx`, quitar la rama `status === 401` y mostrar el error de `actual` desde los errores de campo del 422. Verificar con un test del front (MSW con un 422 en `actual`): el mensaje aparece junto al campo y la sesión no se cierra.

## 5. Listado de cuentas: filtros y búsqueda literal (puntos 7 y 8)

- [x] 5.1 Definir `RolFiltro` y `EstadoFiltro` como `Literal` en `schemas.py` y usarlos en `listar_cuentas` del router. Verificar con tests: `rol=superusuario` y `estado=cualquiera` responden 422, y los `Literal` coinciden con `models.ROLES` y `models.ESTADOS`.
- [x] 5.2 Agregar `_literal(q)` en `servicio.py` y usar `escape="\\"` en las tres comparaciones de la búsqueda. Verificar con un test: con `a_b@example.com` y `axb@example.com`, buscar `a_b` devuelve solo la primera; buscar `%` no devuelve todas las cuentas; la búsqueda de "pérez" sin acento sigue funcionando.

## 6. Sesión en el frontend: refresh y rutas públicas (puntos 1 y 2)

- [x] 6.1 En `client.js`, definir `RUTAS_PUBLICAS_AUTH` (las 7 rutas del gateway) y usarla en `enviar()` (sin `Authorization`) y en `api()` (refresh ante un 401 en cualquier ruta que no esté en la lista). Verificar en `client.test.js`: la lista tiene exactamente las 7 rutas, y una ruta pública se envía sin header aunque haya tokens.
- [x] 6.2 Test: perfil con el token vencido (MSW responde 401 una vez en `GET /api/auth/perfil`) → se llama a `/api/auth/refresh`, se reintenta y se muestra el perfil sin cerrar la sesión. Repetir con `GET /api/auth/admin/usuarios` para el administrador.
- [x] 6.3 Test: restablecimiento con una sesión revocada en memoria (MSW responde 401 si `POST /api/auth/restablecer-contrasenia` llega con `Authorization`) → la solicitud sale sin token, la contraseña se restablece y no se llama a `/api/auth/refresh`.
- [x] 6.4 Test: un login con credenciales inválidas (401) no llama a `/api/auth/refresh` y muestra el error de credenciales; un refresh rechazado en una ruta protegida cierra la sesión con el aviso.
- [x] 6.5 En `Restablecer.jsx`, descartar la sesión guardada al completar el restablecimiento (el backend ya revocó todas las sesiones). Verificar con un test: con una sesión guardada, después de restablecer no quedan tokens y el encabezado muestra "Ingresar" en lugar de "Mi perfil".

## 7. Verificación integral

- [x] 7.1 Correr las suites de auth, gateway, eventos y ventas, más `npm test` y `npm run build` del frontend. Todas en verde, y `openspec validate auth-correcciones-review --strict` sin errores.
- [x] 7.2 Prueba manual con `docker compose up -d --build`:
  - Login de una cuenta bloqueada: da "Email o contraseña incorrectos.".
  - Cambio de contraseña: la sesión sigue abierta.
  - Contraseña actual incorrecta: el error aparece en el campo.
  - Link de restablecimiento abierto en el mismo navegador después de un cambio de contraseña en otra pestaña: funciona.
- [x] 7.3 Responder en el PR #17 los 8 puntos de la review con el commit que corrige cada uno.

## Workflow follow-up

- Archivar el change con `/opsx:archive` cuando el CI del PR #17 esté en verde.
- El usuario hace `git add`, `commit` y `push` a `feature/auth-cuentas-y-perfil`; el PR #17 se actualiza solo.
