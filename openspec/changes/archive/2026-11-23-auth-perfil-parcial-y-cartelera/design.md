# Design

## Context

Ver `proposal.md`. Dos detalles del código actual definen el enfoque:

- El gateway trata como pública **toda** lectura `GET /api/eventos/*`, incluida `GET /api/eventos/mios`. Pero `eventos` exige identidad en `/mios` y muestra los borradores en `/eventos/{id}` solo a su dueño. Para el frontend, "pública según el gateway" no equivale a "se puede leer sin sesión".
- Cuando falla el refresh, `client.js` ya llama a `borrarTokens("sesion_cerrada")`. Los guardas de ruta (`SoloConSesion`, `SoloRol`) reaccionan a esa sesión vacía y llevan al login con el aviso.

## Goals / Non-Goals

**Goals:**
- Que un perfil incompleto se pueda guardar de a un campo, sin aflojar la validación del backend.
- Que las pantallas públicas sigan funcionando con una sesión revocada.

**Non-Goals:**
- Cambiar el gateway para que ignore tokens inválidos en las rutas públicas (descartado en el design de `auth-correcciones-review`).
- Avisar en la cartelera que la sesión se cerró: el encabezado pasa a "Ingresar", y el aviso queda para el login.

## Decisions

### 1. El perfil envía solo los campos modificados

`Perfil.jsx` compara cada campo con el valor cargado del servidor y arma el `PATCH` solo con los distintos. Para `piso_depto`, un `""` viaja como `null` (vaciarlo). Si no cambió nada, no se llama a la API.

- *Alternativa descartada*: omitir los campos vacíos. Escondería el caso en que el usuario borra un obligatorio que tenía valor: con el diff, ese `""` sí viaja y el backend responde 422 en el campo, como corresponde.
- *Alternativa descartada*: que el backend ignore los `""`. Aflojaría la validación de la API para tapar un problema del cliente.

### 2. Lista explícita de lecturas públicas en el frontend

`client.js` define `esLecturaPublica(metodo, ruta)`: `GET` de `/api/eventos`, `/api/eventos/tipos`, `/api/eventos/recintos`, `/api/eventos/{id}` y `/api/ventas/eventos/{id}/disponibilidad`. Ante un 401 cuyo refresh falla:

- **Lectura pública**: se borra la sesión (`borrarTokens("sesion_cerrada")`) y se repite la solicitud una vez, ya sin token. No se llama a `alFallarAuth`.
- **Resto**: igual que hoy (borrar la sesión y `alFallarAuth`, que lleva al login).

`/api/eventos/mios` no está en la lista, así que sigue llevando al login. En `GestionEvento` (`GET /api/eventos/{id}` de un owner), la lectura sin token puede devolver 404 para un borrador, pero el guarda `SoloRol` ya redirige al login porque la sesión quedó vacía.

- *Alternativa descartada*: usar la regla del gateway (cualquier `GET /api/eventos/*`). Incluye `/mios`, que sin sesión no tiene sentido y dejaría al owner en una pantalla de error.

## Risks / Trade-offs

- **[Riesgo]** La lista de lecturas públicas del frontend se desincroniza con las rutas de `eventos` y `ventas` → Si una pantalla pública nueva no está en la lista, cae en el comportamiento seguro (login con aviso). Un test fija la lista.
- **[Trade-off]** En la cartelera, el usuario no ve un aviso explícito de que su sesión se cerró → El encabezado pasa a "Ingresar", y al ir al login no hay sesión activa.
