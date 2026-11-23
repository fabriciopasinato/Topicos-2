# Proposal

## Why

La segunda revisión del PR #17 encontró dos problemas en el frontend:

- **Perfil de owners y admins.** La corrección que rechaza vacíos en los campos obligatorios del perfil dejó a los event owners y a los administradores sin poder guardar su perfil. Esas cuentas se crean sin datos personales, y el frontend manda todos los campos al guardar, con los vacíos como `""`.
- **Cartelera con sesión revocada.** Un usuario con la sesión revocada que abre la cartelera termina en el login, cuando la cartelera es pública.

## What Changes

- **Perfil**: el frontend envía en el `PATCH /api/auth/perfil` solo los campos que el usuario cambió. Un perfil incompleto (owner o admin) se puede completar de a un campo. El backend no cambia: ya acepta ediciones parciales.
- **Lecturas públicas con sesión revocada**: si una lectura pública (cartelera, detalle de evento, tipos, recintos, disponibilidad) responde 401 y el refresh también falla, el frontend descarta la sesión y repite la lectura sin token, sin redirigir al login. En las rutas protegidas sigue el comportamiento actual: se cierra la sesión y se redirige al login con el aviso.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `autenticacion/usuarios-roles`: "Perfil del usuario" suma la edición de un perfil incompleto, y "Sesión del usuario en el frontend" suma las lecturas públicas con la sesión revocada.

## Impact

- **frontend**: `src/pages/Perfil.jsx` (envía solo lo cambiado), `src/api/client.js` (lecturas públicas sin redirigir), y tests en `Perfil.test.jsx` y `SesionAuth.test.jsx`.
- **auth**: un test de API que confirma que un owner sin perfil puede guardar solo el teléfono. No cambia el código.
- **gateway**: sin cambios.
