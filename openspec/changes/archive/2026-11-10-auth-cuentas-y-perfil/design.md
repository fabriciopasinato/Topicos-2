# Diseño técnico: cuentas, perfil y recuperación en auth

## Context

Ver `proposal.md` para el porqué. Punto de partida en el código (Etapa I):

- `services/auth`: tablas `users(email, password_hash, rol, created_at)` y `refresh_tokens` con rotación atómica; argon2id; JWT HS256 con `sub`, `rol`, `iat`, `exp`; endpoints `registro`, `login`, `refresh`, `event-owners`; seed idempotente del admin. Lógica en `app/servicio.py` sin dependencias de HTTP; tests con rollback por test y fixture de concurrencia.
- `gateway`: valida el JWT localmente (`app/seguridad.py`), define rutas públicas en `es_publica()` y grupos de rate limit en `app/rate_limit.py`; ya usa Redis.
- `frontend`: cliente de API con refresh automático (`src/api/client.js`), `SesionProvider` que lee `rol` del token, páginas `Login` y `Registro`, rutas con `SoloConSesion`.
- No hay infraestructura de email.

## Goals / Non-Goals

**Goals:**
- Un único flujo de restablecimiento (token de un solo uso enviado por email) para tres disparadores: "olvidé mi contraseña", bloqueo por intentos y restablecimiento por el admin.
- Que bloquear o cambiar la contraseña corte el acceso al instante, sin que el gateway consulte a auth en cada request.
- No revelar qué emails están registrados en ninguna respuesta pública.
- Enviar emails reales por SMTP en desarrollo sin riesgo de que salgan de la máquina, y pasar a un proveedor real solo con variables de entorno.

**Non-Goals:**
- Historial de eventos de auditoría (quién cambió qué y con qué valor): solo columnas de auditoría en la cuenta.
- Suspender cuentas o darse de baja.
- Validar la edad del comprador en ventas.
- Cola de emails con reintentos (outbox + worker): queda para la Etapa III junto con RabbitMQ.
- Cambiar el email de la cuenta.

## Decisions

### 1. Modelo de la cuenta

`users` suma columnas (todas las de perfil nullables en la base, porque el admin semilla y los event owners no las tienen; el endpoint de registro las exige):

| Columna | Tipo | Notas |
|---|---|---|
| `nombre`, `apellido` | varchar(100) | |
| `dni` | varchar(8) | `UNIQUE` (parcial: `WHERE dni IS NOT NULL`), solo dígitos, 7 u 8 |
| `fecha_nacimiento` | date | pasada, edad ≤ 120 |
| `telefono` | varchar(20) | dígitos, espacios, `+` y `-` |
| `calle`, `numero`, `piso_depto`, `localidad`, `codigo_postal` | varchar | `piso_depto` opcional; CP de 4 dígitos o CPA (`A1234ABC`) |
| `provincia` | varchar(40) | una de las 24 jurisdicciones (lista fija en el código) |
| `estado` | varchar(30) | `pendiente_verificacion`, `activa`, `bloqueada` (CHECK) |
| `motivo_bloqueo` | varchar(30) null | `intentos_fallidos` o `restablecimiento_admin` |
| `intentos_fallidos` | int, default 0 | |
| `updated_at`, `last_login_at` | timestamptz | `created_at` ya existe |

La migración deja a las cuentas existentes en `activa` (ya estaban en uso antes de existir la verificación).

Tabla nueva `tokens_cuenta(id, user_id, tipo, token_hash UNIQUE, expires_at, used_at, created_at)` con `tipo` en `verificacion` / `restablecimiento`. Se guarda solo el SHA-256 del token, como con los refresh tokens. Al emitir un token nuevo de un tipo, los anteriores sin usar del mismo usuario y tipo se marcan como usados (solo sirve el último).

- **Alternativa descartada: tabla de perfil separada.** El perfil es 1 a 1 con la cuenta y siempre se lee junto; separarlo agrega joins sin beneficio.
- **Alternativa descartada: guardar la provincia como texto libre.** Generaría variantes del mismo valor ("Bs As", "Buenos Aires").

### 2. Estados de la cuenta

```
 registro --> pendiente_verificacion --(token de verificacion)--> activa
                      |                                             |   ^
                      +---(restablecimiento completo)---------------+   |
                                                                    |   |
              5 intentos fallidos / admin restablece                v   |
                                                              bloqueada |
                                                                    |   |
                              (restablecimiento completo) ----------+---+
```

Solo `activa` puede loguearse. Los dos motivos de bloqueo se resuelven igual: completando un restablecimiento. Completarlo también verifica el email, porque prueba que el usuario controla esa casilla.

- **Alternativa descartada: un estado distinto por motivo.** Ambos casos se comportan igual; el motivo queda en `motivo_bloqueo` para el mensaje y el panel de admin.

### 3. Login sin revelar qué cuentas existen

Orden de verificación en `login`:

1. Se busca el usuario y se verifica la contraseña siempre (con un hash ficticio si no existe, como hoy, para igualar el tiempo).
2. Contraseña incorrecta: si la cuenta existe y está `activa`, se incrementa el contador (decisión 4). Siempre se responde `401 {codigo: "credenciales_invalidas"}`, también si la cuenta está bloqueada o sin verificar.
3. Contraseña correcta y cuenta no activa: `403 {codigo: "email_no_verificado" | "cuenta_bloqueada"}`.
4. Contraseña correcta y cuenta activa: contador en 0, `last_login_at = now()`, emisión de tokens.

Así el estado solo se revela a quien conoce la contraseña.

### 4. Bloqueo atómico al 5º intento

Un único `UPDATE` hace el conteo y la transición:

```sql
UPDATE users
   SET intentos_fallidos = intentos_fallidos + 1,
       estado = CASE WHEN intentos_fallidos + 1 >= 5 THEN 'bloqueada' ELSE estado END,
       motivo_bloqueo = CASE WHEN intentos_fallidos + 1 >= 5 THEN 'intentos_fallidos' ELSE motivo_bloqueo END
 WHERE id = :id AND estado = 'activa'
RETURNING intentos_fallidos, estado
```

Con varios intentos simultáneos, PostgreSQL serializa los `UPDATE` sobre la fila; solo el que devuelve `intentos_fallidos = 5` dispara el bloqueo (revocación y email), y los siguientes ya no matchean `estado = 'activa'`. Exactamente un email por bloqueo.

Riesgo conocido: cualquiera puede bloquear una cuenta ajena conociendo el email. Lo mitigan el rate limit por IP del grupo `auth` y que desbloquear solo requiere acceso a la casilla de email del dueño (ver Risks).

### 5. Política de contraseñas

Una sola función `validar_contrasenia(contrasenia, email)` usada por registro, cambio y restablecimiento:

- longitud entre 10 y 128 (el máximo evita que alguien haga hashear textos enormes);
- no figura en `app/data/contrasenias_comunes.txt` (las 10.000 más comunes de SecLists, licencia MIT), comparando en minúsculas; se carga una vez en un `frozenset`;
- tampoco su **palabra base**: se le quitan los números y símbolos del final y se vuelve a buscar (`password123` → `password`, `dragon2024!` → `dragon`). Hace falta porque, con un mínimo de 10 caracteres, solo 51 de las 10.000 entradas tienen ese largo: el resto ya lo rechaza la longitud, y las variantes "palabra común + números" son justamente las que quedarían pasando;
- distinta del email, sin distinguir mayúsculas;
- sin reglas de composición (mayúscula, número, símbolo): empujan a contraseñas predecibles como `Password1!`.

Los errores se devuelven como 422 con un mensaje por regla, para que el frontend los muestre.

### 6. Tokens de cuenta y emails

| Email | Disparador | Link | Vigencia |
|---|---|---|---|
| Verificá tu cuenta | registro, reenvío | `{FRONTEND_URL}/verificar?token=` | 24 h |
| Restablecé tu contraseña | olvidé mi contraseña | `{FRONTEND_URL}/restablecer?token=` | 30 min |
| Tu cuenta se bloqueó | 5º intento fallido | `{FRONTEND_URL}/restablecer?token=` | 30 min |
| Un administrador restableció tu contraseña | admin | `{FRONTEND_URL}/restablecer?token=` | 30 min |

Consumir un token es un `UPDATE tokens_cuenta SET used_at = now() WHERE token_hash = :h AND tipo = :t AND used_at IS NULL AND expires_at > now() RETURNING user_id`. Dos usos simultáneos del mismo token: solo uno obtiene fila (mismo patrón que la rotación del refresh token).

**Envío:** `app/email.py` define una interfaz `EnviadorEmail` con una implementación SMTP (`smtplib` de la biblioteca estándar) y una falsa para tests que acumula los mensajes en una lista. La implementación se inyecta como dependencia de FastAPI. El envío se hace **en segundo plano** con `BackgroundTasks`, después de confirmar la transacción: la respuesta no espera al SMTP y un SMTP caído no hace fallar el registro. Si el envío falla, se registra en el log y el usuario puede pedir un reenvío o un nuevo restablecimiento.

- **Alternativa descartada: enviar dentro del request.** Un SMTP lento o caído haría lento o fallido el registro.
- **Alternativa para la Etapa III: outbox + worker.** Una tabla de emails pendientes escrita en la misma transacción y un worker que los envía con reintentos. Se adopta cuando exista RabbitMQ y la infraestructura de workers.

Los endpoints públicos de reenvío y "olvidé mi contraseña" responden siempre `202`, exista o no la cuenta, y solo envían email si corresponde.

### 7. Servidor de email de desarrollo: Mailpit

Contenedor `mailpit` (`axllent/mailpit`) en el compose, **sin ningún puerto publicado**, igual que postgres, redis y los microservicios:
- SMTP en `mailpit:1025` y bandeja (web y API) en `mailpit:8025`, ambos solo en la red interna;
- se mantiene la regla de la Etapa I: solo frontend y gateway son accesibles desde fuera de Docker;
- sin volumen: los emails se pierden al recrear el contenedor, lo cual es deseable en desarrollo.

Como la bandeja contiene links de restablecimiento, exponerla (aunque sea en la red local) permitiría a otra persona de la misma red tomar cuentas del entorno de desarrollo. Para leerla sin publicar puertos se documentan dos formas en el README:

1. **Por consola**, consultando la API desde un contenedor que ya está en la red: `docker compose exec auth python -c "import urllib.request; print(urllib.request.urlopen('http://mailpit:8025/api/v1/messages').read().decode())"`.
2. **Túnel temporal y solo local**, cuando se quiere la bandeja visual (por ejemplo, en la defensa): `docker run --rm --network ticketera_net -p 127.0.0.1:8025:8025 alpine/socat TCP-LISTEN:8025,fork TCP:mailpit:8025`. Escucha solo en `127.0.0.1` (no es alcanzable desde otra máquina) y deja de existir al cortarlo con Ctrl+C.

Auth lee `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS` y `EMAIL_FROM`. En producción se reemplazan por los de un proveedor (SendGrid, SES); no hay contenedor de email.

- **Alternativa descartada: publicar la bandeja en `0.0.0.0:8025`.** Cualquiera en la misma red podría leer los links de restablecimiento.
- **Alternativa descartada: publicarla en `127.0.0.1:8025` de forma permanente.** No es alcanzable desde otra máquina, pero sería una excepción fija a la regla de puertos; el túnel temporal da lo mismo solo cuando hace falta.
- **Alternativa descartada: escribir los emails en el log de auth.** Evita un contenedor, pero exige un "modo log" distinto del SMTP real.

### 8. Revocación inmediata con Redis

Al bloquear una cuenta, restablecerla (admin) o cambiar o restablecer la contraseña:

1. En `auth_db`: se marcan como usados todos los refresh tokens del usuario.
2. En Redis: `SET revocado:<user_id> <epoch_segundos> EX <JWT_ACCESS_TTL_MINUTES * 60>`. Pasado ese tiempo, cualquier token anterior ya venció solo, así que la clave expira sin dejar basura.

En el gateway, después de validar firma y expiración: `GET revocado:<sub>`. Si existe y `iat < valor`, responde 401. La comparación es estricta: un token emitido en el mismo segundo que la revocación (por ejemplo, el nuevo par que entrega el cambio de contraseña) sigue siendo válido. Esa ventana de un segundo se acepta.

**Fallas:** si Redis no responde al escribir, auth completa igual la operación (los refresh tokens ya quedaron revocados en la base) y registra el error; el token de acceso viejo vive hasta su vencimiento. Si Redis no responde al leer, el gateway deja pasar (fail-open), igual que el rate limit, y registra el error.

| Comunicación | Tipo |
|---|---|
| auth -> Redis (`SET revocado:*`) | Sync (TCP), en la misma operación de negocio |
| gateway -> Redis (`GET revocado:*`) | Sync (TCP), por cada request con token |
| auth -> Mailpit / proveedor SMTP | Sync (SMTP), en segundo plano después de responder |
| frontend -> gateway -> auth | Sync (HTTP), como hasta ahora |

No hay comunicación asíncrona por colas en este change.

- **Alternativa descartada: acortar el token de acceso a 15 minutos.** Reduce la ventana pero no la elimina, y obliga a refrescar mucho más seguido.
- **Alternativa descartada: que el gateway consulte a auth en cada request.** Rompe la decisión de la Etapa I de que el sistema siga funcionando con auth caído.
- **Sobre compartir Redis:** Redis es infraestructura compartida (como la red), no la base de otro servicio. La clave `revocado:*` es un contrato explícito entre auth (único que escribe) y gateway (único que lee), documentado acá.

### 9. Auditoría: `updated_at` con trigger

La migración crea una función `set_updated_at()` y un trigger `BEFORE UPDATE ON users` que asigna `NEW.updated_at = now()`. Se usa un trigger y no `onupdate` de SQLAlchemy porque auth ya hace `UPDATE` en SQL directo (contador de intentos, rotación), que el ORM no intercepta.

`last_login_at` se actualiza solo en un login con contraseña exitoso; renovar con refresh token no lo cambia.

### 10. API

Bajo `/auth` en el servicio (`/api/auth` vía gateway):

| Método y ruta | Acceso | Respuesta |
|---|---|---|
| `POST /auth/registro` | público | 201 (contrato ampliado) |
| `POST /auth/verificar-email` `{token}` | público | 200 / 400 |
| `POST /auth/reenviar-verificacion` `{email}` | público | 202 siempre |
| `POST /auth/login` | público | 200 / 401 / 403 con `codigo` |
| `POST /auth/olvide-contrasenia` `{email}` | público | 202 siempre |
| `POST /auth/restablecer-contrasenia` `{token, contrasenia}` | público | 200 / 400 / 422 |
| `GET /auth/perfil`, `PATCH /auth/perfil` | autenticado | 200 |
| `POST /auth/perfil/contrasenia` `{actual, nueva}` | autenticado | 200 con tokens nuevos / 401 / 422 |
| `GET /auth/admin/usuarios?q=&rol=&estado=&pagina=&tamanio=` | admin | 200 `{items, total}` |
| `GET /auth/admin/usuarios/{id}` | admin | 200 / 404 |
| `POST /auth/admin/usuarios/{id}/restablecer-contrasenia` | admin | 202 |

Los errores de login llevan `{"detail": ..., "codigo": ...}` para que el frontend distinga los casos sin parsear texto.

En el gateway: las cuatro rutas públicas nuevas se suman a `es_publica()` y al grupo `auth` de `rate_limit.grupo_de()`.

**Corrección encontrada en la verificación integrada: CORS como capa externa del gateway.** En la Etapa I, CORS quedaba *dentro* del pipeline (para que los preflight `OPTIONS` quedaran en la bitácora). Pero las respuestas que genera el propio pipeline (401 por token inválido o revocado, 429 por rate limit) cortaban antes de pasar por CORS y salían sin `Access-Control-Allow-Origin`. El navegador las bloqueaba y el frontend solo veía un error de red: no podía renovar el token, mostrar "tu sesión se cerró" ni leer `Retry-After`. Los tests con MSW no lo detectaban porque no aplican CORS. Ahora CORS es la capa más externa y hay tests que verifican los headers en 401 y 429. Costo aceptado: los preflight `OPTIONS` los responde CORS y no se registran en la bitácora (las solicitudes reales sí, todas).

### 11. Frontend

- **Registro:** un único formulario con tres secciones (datos personales, dirección, cuenta), con validación en vivo de lo que el cliente puede comprobar (longitud de contraseña, coincidencia de las dos, DNI numérico, provincia de una lista) y los errores 422 del backend mostrados por campo. Al terminar, pantalla "Te enviamos un email para verificar tu cuenta".
  - Alternativa descartada: asistente de 3 pasos. Se ve mejor, pero suma estado entre pasos y más tests sin cambiar el comportamiento.
- **Páginas nuevas:** `/verificar`, `/olvide`, `/restablecer`, `/perfil`, `/perfil/contrasenia`, `/admin/usuarios`, `/admin/usuarios/:id`, `/admin/event-owners`.
- **Login:** maneja `credenciales_invalidas`, `email_no_verificado` (con botón de reenvío) y `cuenta_bloqueada` (aviso de revisar el email), y suma el link a "Olvidé mi contraseña".
- **Navegación por rol:** guarda `SoloRol` (análoga a `SoloConSesion`) y menú "Administración" solo para `administrador`.
- **Cambio de contraseña:** guarda el par de tokens nuevo que devuelve el backend, así la sesión actual sigue.
- **Sesión revocada:** si el refresh falla después de un 401, el aviso pasa a "Tu sesión se cerró. Volvé a ingresar".
- Tests con Vitest, Testing Library y MSW, sin backend.

## Risks / Trade-offs

- [Cualquiera puede bloquear una cuenta ajena con 5 intentos] -> Rate limit por IP del grupo `auth` (10 por minuto) y desbloqueo que solo requiere la casilla de email del dueño. Es el mismo esquema que usan los bancos; se acepta.
- [Emails perdidos si auth se reinicia mientras envía en segundo plano] -> El usuario puede pedir un reenvío o un nuevo restablecimiento. Outbox con reintentos en la Etapa III.
- [Redis caído al revocar] -> Los refresh tokens se revocan igual en la base; el token de acceso viejo vive hasta su vencimiento (máximo `JWT_ACCESS_TTL_MINUTES`). Queda en el log.
- [Ventana de un segundo en la comparación `iat < revocado`] -> Se acepta para que el par nuevo del cambio de contraseña no quede revocado.
- [Redis compartido entre auth y gateway] -> Contrato acotado a la clave `revocado:*`, documentado en este design y con tests en ambos lados.
- [Datos personales (DNI, dirección, fecha de nacimiento)] -> Solo los ven el propio usuario y el admin; nunca viajan en el JWT ni a otros servicios. Su eliminación o anonimización queda para un change de baja de cuenta.
- [`POST /auth/registro` cambia de contrato] -> El frontend se actualiza en el mismo change; no hay otros consumidores.
- [Cambio en el gateway, módulo de otro integrante] -> Se acota a dos piezas (verificación de revocación y rutas nuevas) en un grupo de tareas propio.

## Migration Plan

1. Migración Alembic de auth: columnas nuevas, tabla `tokens_cuenta`, índice único parcial de DNI, CHECK de estado, función y trigger de `updated_at`. Los usuarios existentes quedan `activa` con `intentos_fallidos = 0` y `updated_at = created_at`. El `downgrade` revierte todo.
2. Agregar `mailpit` al compose y las variables nuevas a `.env.example`. Quien ya tiene un `.env` debe sumar las variables nuevas (se documenta en el README).
3. Desplegar auth y gateway juntos: el gateway sin la verificación de revocación sigue funcionando (solo no corta al instante), así que el orden no rompe nada.
4. Rollback: `alembic downgrade -1` en auth y volver a la versión anterior de los contenedores.
