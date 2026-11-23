# Design

## Context

El motivo y el alcance están en `proposal.md`; el comportamiento esperado, en `specs/autenticacion/usuarios-roles/spec.md`. Este documento explica cómo se resuelve cada punto con el código actual.

Lo que importa del estado actual:

- **Frontend (`src/api/client.js`)**: `enviar()` agrega `Authorization` a todas las solicitudes. `api()` solo intenta el refresh cuando la ruta no empieza con `/api/auth/`. Esa regla era correcta en la Etapa I, cuando auth solo tenía rutas públicas. Hoy deja afuera `/api/auth/perfil`, `/api/auth/admin/*` y `/api/auth/event-owners`.
- **Gateway**: si llega un `Authorization`, lo valida aunque la ruta sea pública. Un token vencido o revocado da 401 incluso en `POST /api/auth/restablecer-contrasenia`.
- **Revocación**: el servicio anota los user_id en `Efectos.revocaciones`. Después del commit, `Ejecutor.aplicar()` llama a `revocacion.publicar()`, que toma `int(time.time())` en ese momento. El gateway rechaza los tokens con `iat < marca`. En el cambio de contraseña, el token nuevo se firma *antes* del commit y la marca se toma *después*: si en el medio cambia el segundo, la marca queda mayor que el `iat` y el token nuevo nace revocado.
- **Login**: con una contraseña incorrecta, solo cuenta el intento si la cuenta está `activa`. Con la contraseña correcta, una cuenta no activa responde 403 con su código. Así, el 403 `cuenta_bloqueada` le confirma a quien prueba que acertó la contraseña.
- **Perfil**: `PerfilPatch` declara todos los campos `X | None = None`, y `editar_perfil()` copia el valor tal cual. Un `null` explícito llega a la base y termina en dato vacío o en error 500 por NOT NULL.
- **Listado de cuentas**: `Query(enum=...)` solo documenta en OpenAPI, no valida. La búsqueda arma `f"%{q}%"` sin escapar el texto.

## Goals / Non-Goals

**Goals:**
- Corregir los 8 puntos sin cambiar el esquema de la base ni el contrato entre auth y el gateway (`revocado:<user_id>` = epoch en segundos).
- Que cada punto tenga al menos un test que falle con el código actual y pase con la corrección.

**Non-Goals:**
- Cambiar el gateway para que ignore el token en las rutas públicas (ver la decisión 2).
- Contar como intento fallido la contraseña actual incorrecta en el cambio de contraseña: el usuario ya está autenticado, y el endpoint queda alcanzado por el rate limit general del gateway.
- Revisar la resolución en segundos de `iat` y de la marca. Se mantiene, con el límite descrito en Riesgos.

## Decisions

### 1. Rutas públicas de auth como lista explícita en el frontend

`client.js` define `RUTAS_PUBLICAS_AUTH`, con las mismas 7 rutas que `gateway/app/seguridad.py`. A partir de esa lista:

- `enviar()` no agrega `Authorization` si la ruta está en la lista.
- `api()` intenta el refresh ante un 401 en cualquier ruta que *no* esté en la lista.

En la lista, un 401 es una respuesta de negocio, como "credenciales inválidas" en el login o "refresh inválido". No es una sesión vencida, y renovar ahí sería incorrecto o recursivo.

- *Alternativa descartada*: invertir la regla y excluir por prefijo solo `/api/auth/` menos `perfil`/`admin`/`event-owners`. Es frágil, porque cada ruta protegida nueva de auth tendría que acordarse de esa excepción. La lista de rutas públicas cambia mucho menos y ya existe del lado del gateway.
- *Duplicación*: la lista queda en dos lugares, gateway y frontend. Un test del frontend fija las 7 rutas, así un cambio en una lista obliga a mirar la otra. No se comparte por código porque viven en lenguajes y despliegues distintos.

### 2. El gateway no cambia

El fix del punto 2 es que el frontend no mande el token a las rutas públicas. El gateway sigue con su regla: si llega un token, tiene que ser válido.

- *Alternativa considerada*: que el gateway ignore el `Authorization` en las 7 rutas públicas de auth. Es más robusto frente a otros clientes, pero cambia la spec del gateway y su comportamiento ante tokens inválidos, que hoy se registran en la bitácora como 401. Queda como mejora posible. Para el único cliente que existe alcanza con el frontend.

### 3. El instante de revocación viaja en `Efectos`

`Efectos.revocaciones` pasa a ser una lista de `(user_id, instante | None)`. `Ejecutor.aplicar()` llama a `publicar(redis, user_id, ttl, instante)`; `publicar()` ya acepta `instante` y usa `time.time()` solo cuando viene `None`.

- `cambiar_contrasenia()` toma `instante = int(time.time())` **antes** de `_emitir_tokens()` y lo anota con la revocación. El `iat` del token nuevo (`datetime.now()` truncado a segundos por PyJWT) es entonces `>= instante`. El gateway, que rechaza `iat < marca`, lo acepta.
- El bloqueo por intentos, el restablecimiento por email y el restablecimiento por el admin siguen con `None`, es decir con el instante posterior al commit. No emiten tokens nuevos, así que no tienen esta carrera, y tomar la marca más tarde es más estricto con las sesiones viejas.

- *Alternativa descartada*: publicar la marca como `instante - 1`, o comparar con `<=` en el gateway. Cualquiera de las dos cambia el contrato y deja vivos más tokens viejos que la solución elegida.

### 4. Login: el estado se evalúa después de la contraseña, con respuestas iguales para "bloqueada"

Orden en `servicio.login()`:

1. Se verifica la contraseña siempre, como ahora (con un hash ficticio si el email no existe).
2. **Incorrecta**: si la cuenta existe y está `activa` o `pendiente_verificacion`, se registra el intento (UPDATE atómico, que ahora admite los dos estados). Se lanza `CredencialesInvalidas`.
3. **Correcta y `bloqueada`**: se lanza `CredencialesInvalidas`, sin tocar la base, igual que una incorrecta sobre una bloqueada. El cuerpo y el status salen del mismo handler, así que son idénticos.
4. **Correcta y `pendiente_verificacion`**: se reinicia el contador (`intentos_fallidos = 0`, commit) y se lanza `CuentaNoActiva("email_no_verificado")`.
5. **Correcta y `activa`**: igual que ahora.

`CuentaNoActiva` queda con un solo código posible y el router quita el mensaje de `cuenta_bloqueada`. El frontend no tenía lógica propia para ese código (solo un test), así que no cambia su comportamiento.

Una cuenta pendiente bloqueada por intentos queda con `motivo_bloqueo = intentos_fallidos` y recibe el email de bloqueo con el link de restablecimiento. Usar el link la deja `activa`, regla que ya existe: probar el acceso al email equivale a verificarlo.

- *Alternativa descartada*: que también la cuenta pendiente responda el 401 genérico. Se pierde el botón "Reenviar email de verificación", que necesita saber que la cuenta está pendiente. El riesgo de oráculo en las pendientes queda acotado por el contador nuevo y el rate limit.

### 5. Perfil: `null` explícito rechazado en el esquema

`PerfilPatch` agrega un `field_validator(mode="before")` sobre los campos obligatorios, que rechaza `None` con 422. Pydantic solo lo ejecuta cuando el campo viene en el cuerpo, así que se distingue "no lo mandé" (no se valida y no cambia) de "lo mandé en null" (error). El error sale con `loc` en el campo, igual que el resto de la validación de FastAPI, y el frontend lo muestra junto al campo.

- *Alternativa descartada*: un `model_validator` que recorra `model_fields_set`. El error saldría con `loc: ["body"]`, sin el campo, y el frontend no podría mostrarlo en su lugar.

En el frontend, `Perfil.jsx` convierte `""` en `null` solo para `piso_depto`. Los obligatorios vacíos se mandan como `""`, que el backend ya rechaza por `min_length`.

- *Alternativa descartada*: filtrar los `None` en `editar_perfil()` y ignorarlos sin avisar. Oculta el error del cliente y no permite vaciar `piso_depto`.

### 6. Contraseña actual incorrecta → 422 en `actual`

El router convierte `CredencialesInvalidas` en `_error_campo("actual", ["La contraseña actual no es correcta."])`, el mismo formato que los demás 422. `CambiarContrasenia.jsx` ya muestra los errores de campo de un 422, así que solo se quita la rama `status === 401`.

### 7. Filtros con `Literal`

`schemas.py` define `RolFiltro = Literal["administrador", "event_owner", "cliente"]` y `EstadoFiltro = Literal["pendiente_verificacion", "activa", "bloqueada"]`, que el router usa como tipo de `rol` y `estado`. FastAPI los valida y responde 422 con un valor inválido. Un test compara estos `Literal` con `models.ROLES` y `models.ESTADOS`, para que no se desincronicen.

### 8. Búsqueda literal con escape explícito

Una función `_literal(q)` escapa `\`, `%` y `_` con `\`, y las comparaciones usan `ilike(..., escape="\\")` (o `like` para el DNI). Así se mantiene `unaccent` en el apellido. `contains(autoescape=True)` no sirve acá, porque el patrón pasa por `func.unaccent` y `autoescape` solo acepta un string literal.

## Risks / Trade-offs

- **[Riesgo] Tokens viejos firmados en el mismo segundo que el cambio de contraseña siguen valiendo** (`iat == marca`) → Es un margen de menos de un segundo. Sus refresh tokens ya quedan revocados y el access vence solo. Se acepta antes que cortar la sesión nueva.
- **[Riesgo] Las dos listas de rutas públicas (gateway y frontend) se desincronizan** → Un test del frontend fija las 7 rutas, y el design de ambos lados apunta al otro.
- **[Trade-off] Una cuenta bloqueada no ve "tu cuenta está bloqueada" en el login** → El email de bloqueo o de restablecimiento ya se lo explica, y el login sigue ofreciendo "Olvidé mi contraseña".
- **[Riesgo] Clientes que dependían del 401 en el cambio de contraseña o del 403 `cuenta_bloqueada`** → El único cliente es el frontend de este repo, que se actualiza en el mismo change.
- **[Riesgo] Un usuario pendiente que escribe mal la contraseña 5 veces queda bloqueado** → Recibe el email de bloqueo con un link que además verifica la cuenta. Es el mismo camino que una cuenta activa.

## Migration Plan

No hay migraciones de base. Backend y frontend se despliegan juntos con `docker compose up -d --build`. Los tokens y las marcas de revocación ya emitidos siguen siendo válidos con el código nuevo. Rollback: volver al commit anterior, sin pasos de datos.
