# Tasks: cuentas, perfil y recuperación en auth

Los grupos 1 a 9 son de auth y siguen su orden. El grupo 10 (gateway) es independiente y lo puede tomar quien mantiene el gateway en paralelo; solo comparte el contrato de la clave `revocado:<user_id>` en Redis (design, decisión 8). El grupo 11 (frontend) puede arrancar con MSW apenas esté fijado el contrato de la API (design, decisión 10).

## 1. Infraestructura: email de desarrollo y configuración

- [x] 1.1 Agregar el contenedor `mailpit` al `docker-compose.yml` sin ningún puerto publicado (SMTP 1025 y bandeja 8025 solo en la red interna), con healthcheck y `restart: unless-stopped`, y que `auth` dependa de él y de `redis` en estado healthy. Verificar con `docker compose config` (solo frontend y gateway con `ports`), `docker compose up -d` (todo healthy), los puertos 1025 y 8025 cerrados desde el host, y la API de la bandeja respondiendo desde el contenedor `auth`.
- [x] 1.2 Agregar a `.env.example` y al servicio `auth` en el compose `REDIS_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS`, `EMAIL_FROM` y `FRONTEND_URL`, y a `Settings` de auth con sus valores por defecto. Verificar con un test de configuración que las variables se leen y con `docker compose config`.
- [x] 1.3 Actualizar el README: cómo leer los emails sin publicar puertos (consulta por consola a la API desde `auth` y túnel temporal a `127.0.0.1:8025`), variables nuevas del `.env` para quien ya tiene uno, y cómo pasar a un proveedor SMTP real. Verificar siguiendo el README: leer un email por consola, abrir la bandeja con el túnel, confirmar que desde otra IP no se llega, y cortar el túnel.

## 2. Auth: modelo de datos y migración

- [x] 2.1 Ampliar el modelo `Usuario` con datos personales, dirección, `estado`, `motivo_bloqueo`, `intentos_fallidos`, `updated_at` y `last_login_at`, y crear el modelo `TokenCuenta`. Verificar que la app importa sin errores y que los tests existentes siguen pasando.
- [x] 2.2 Crear la migración Alembic: columnas nuevas, CHECK de `estado` y `motivo_bloqueo`, índice único parcial de `dni`, tabla `tokens_cuenta`, función y trigger `set_updated_at`, y cuentas existentes en `activa` con `updated_at = created_at`. Verificar con tests de integración: la migración aplica y revierte, un `UPDATE` en SQL directo cambia `updated_at`, el CHECK rechaza un estado inválido y el índice rechaza un DNI duplicado.
- [x] 2.3 Actualizar el seed del administrador y el alta de event owners para crear cuentas `activa`. Verificar con los tests existentes de seed y alta, ajustados para comprobar el estado.

## 3. Auth: política de contraseñas

- [x] 3.1 Agregar `app/data/contrasenias_comunes.txt` (10.000 más comunes de SecLists, MIT, con la atribución en el encabezado) e implementar `validar_contrasenia(contrasenia, email)`. Verificar con tests unitarios: 9 caracteres, 10 caracteres, 128, 129, `password123`, `1234567890`, igual al email con otras mayúsculas y una frase larga sin símbolos aceptada.

## 4. Auth: tokens de cuenta y envío de emails

- [x] 4.1 Implementar la emisión de tokens de cuenta (verificación 24 h, restablecimiento 30 min, solo hash en la base, invalidación de los anteriores del mismo tipo) y el consumo atómico. Verificar con tests: token vigente, vencido, usado, solo sirve el último emitido, y un test de concurrencia con dos consumos simultáneos del mismo token donde solo uno gana.
- [x] 4.2 Implementar `app/email.py`: interfaz `EnviadorEmail`, implementación SMTP con `smtplib`, implementación falsa para tests, inyección como dependencia y plantillas de los 4 emails con el link armado desde `FRONTEND_URL`. Verificar con tests unitarios que cada plantilla contiene el link correcto y ninguna contraseña, y que el enviador SMTP llega a un servidor SMTP de prueba levantado en el test.

## 5. Auth: registro ampliado y verificación de email

- [x] 5.1 Ampliar `POST /auth/registro` con los datos personales y la dirección (validación de DNI, teléfono, fecha de nacimiento, provincia de la lista de 24 y código postal), la política de contraseñas, el estado `pendiente_verificacion` y el envío del email de verificación en segundo plano. Verificar con tests de integración: registro exitoso con email enviado al enviador falso, rol en el cuerpo ignorado, email y DNI duplicados con 409, cada dato inválido con 422, y un test de concurrencia con dos registros simultáneos del mismo DNI.
- [x] 5.2 Implementar `POST /auth/verificar-email` y `POST /auth/reenviar-verificacion`. Verificar con tests: verificación exitosa que deja la cuenta `activa`, token vencido o usado con 400, reenvío que invalida el token anterior, y reenvío para email inexistente o ya verificado con 202 sin email enviado.

## 6. Auth: login con estados, bloqueo y revocación

- [x] 6.1 Implementar la escritura de revocación en Redis (`revocado:<user_id>` con TTL igual al del token de acceso) junto con la invalidación de refresh tokens en una función única. Verificar con tests de integración contra el Redis de test: la clave existe con el instante y el TTL correctos, los refresh tokens dejan de servir, y con Redis caído la operación se completa y el error queda en el log.
- [x] 6.2 Modificar el login: contraseña siempre verificada, 401 `credenciales_invalidas` sin revelar el estado, 403 `email_no_verificado` o `cuenta_bloqueada` solo con contraseña correcta, contador en 0 y `last_login_at` en el login exitoso, e `iat` en el token. Verificar con tests de cada caso de la spec, incluido que un refresh no cambia `last_login_at`.
- [x] 6.3 Implementar el bloqueo al 5º intento fallido con el `UPDATE` atómico, la revocación y el email de bloqueo. Verificar con tests: el 5º intento bloquea, un login exitoso reinicia el contador, y un test de concurrencia con 4 intentos simultáneos sobre una cuenta con 3 fallidos que termina bloqueada con exactamente un email enviado.

## 7. Auth: recuperación y restablecimiento de contraseña

- [x] 7.1 Implementar `POST /auth/olvide-contrasenia` (202 siempre, email solo si la cuenta existe) y `POST /auth/restablecer-contrasenia` (política de contraseñas, cuenta `activa` y verificada, contador en 0, revocación de sesiones). Verificar con tests: pedido para email existente e inexistente con la misma respuesta, restablecimiento que desbloquea una cuenta bloqueada, que activa una cuenta sin verificar, token vencido o reutilizado con 400, contraseña inválida con 422 y login con la nueva contraseña.

## 8. Auth: perfil y cambio de contraseña

- [x] 8.1 Implementar `GET /auth/perfil` y `PATCH /auth/perfil` (email, DNI, rol y estado no editables). Verificar con tests: datos y campos de auditoría en la respuesta sin el hash, edición de la dirección que actualiza `updated_at`, y `rol`, `email` y `dni` ignorados en la edición.
- [x] 8.2 Implementar `POST /auth/perfil/contrasenia` con la contraseña actual, la política, la revocación y la entrega de un par de tokens nuevo. Verificar con tests: cambio exitoso, actual incorrecta con 401, nueva inválida con 422, y que el refresh token anterior deja de servir mientras el nuevo funciona.

## 9. Auth: administración de cuentas

- [x] 9.1 Implementar `GET /auth/admin/usuarios` (búsqueda por email, apellido o DNI sin distinguir mayúsculas ni tildes, filtros por rol y estado, paginación con total) y `GET /auth/admin/usuarios/{id}`. Verificar con tests: búsqueda paginada sobre 30 cuentas, filtros, detalle sin hash, inexistente con 404, y 403 para cliente y event owner.
- [x] 9.2 Implementar `POST /auth/admin/usuarios/{id}/restablecer-contrasenia`: cuenta `bloqueada` con motivo `restablecimiento_admin`, revocación y email. Verificar con tests: la contraseña anterior deja de servir (403 `cuenta_bloqueada` al loguearse), el email llega con el link, la respuesta no contiene contraseñas, y 403 para no admin.

## 10. Gateway: revocación y rutas de recuperación

- [x] 10.1 Agregar la verificación de `revocado:<sub>` en Redis después de validar el JWT (rechazo si `iat < revocado`, fail-open con log si Redis no responde). Verificar con tests: token anterior a la revocación con 401 sin llamar al servicio, token posterior aceptado, token del mismo segundo aceptado, y Redis caído que deja pasar.
- [x] 10.2 Sumar las rutas públicas nuevas (`verificar-email`, `reenviar-verificacion`, `olvide-contrasenia`, `restablecer-contrasenia`) a `es_publica()` y al grupo de rate limit `auth`. Verificar con tests: las cuatro rutas se reenvían sin token, comparten el límite con el login y responden 429 con `Retry-After` al superarlo.

## 11. Frontend

- [x] 11.1 Ampliar `/registro` con las tres secciones (datos personales, dirección, cuenta), validación en vivo, lista de provincias, errores 422 por campo y pantalla final de "revisá tu email". Verificar con tests de componentes con MSW: registro exitoso, contraseñas que no coinciden, contraseña corta, DNI duplicado (409) y error de campo devuelto por el backend.
- [x] 11.2 Modificar `/login` para manejar `credenciales_invalidas`, `email_no_verificado` (con botón de reenvío) y `cuenta_bloqueada`, y agregar el link a "Olvidé mi contraseña". Verificar con tests de componentes de los tres códigos y del reenvío.
- [x] 11.3 Crear `/verificar`, `/olvide` y `/restablecer` (leen el token de la URL). Verificar con tests: verificación exitosa y token vencido, pedido de restablecimiento con el mismo mensaje exista o no el email, restablecimiento exitoso que lleva al login con aviso, token vencido y contraseñas que no coinciden.
- [x] 11.4 Crear `/perfil` y `/perfil/contrasenia`, con el guardado del par de tokens nuevo tras el cambio. Verificar con tests: ver y editar datos, cambio exitoso que mantiene la sesión, contraseña actual incorrecta.
- [x] 11.5 Crear la guarda `SoloRol`, el menú "Administración" y las páginas `/admin/usuarios`, `/admin/usuarios/:id` y `/admin/event-owners`. Verificar con tests: búsqueda y paginación, detalle con estado y auditoría, restablecimiento con confirmación, alta de event owner, y un cliente que entra a `/admin` y es redirigido.
- [x] 11.6 Cambiar el aviso del cliente de API cuando falla el refresh a "Tu sesión se cerró. Volvé a ingresar". Verificar con el test existente del cliente, ajustado.

## 12. CI y verificación integrada

- [ ] 12.1 Verificar que el workflow de CI existente corre todos los tests nuevos de auth, gateway y frontend en el PR (incluido el Redis de test para auth), ajustando `.github/workflows/tests.yml` si hace falta. Verificar con el PR a `dev` en verde.
- [x] 12.2 Con `docker compose up -d`, recorrer de punta a punta desde el frontend: registro, email en Mailpit (leído con el túnel temporal o por consola), verificación, login, edición del perfil, cambio de contraseña, 5 intentos fallidos con bloqueo y email, restablecimiento desde el link, login con la nueva, y restablecimiento por el admin que corta al instante la sesión abierta del usuario en otra pestaña.

## Workflow follow-up

- Abrir el PR de `feature/auth-cuentas-y-perfil` a `dev` con el CI en verde.
- Archivar el change con `/opsx:archive` una vez mergeado.
