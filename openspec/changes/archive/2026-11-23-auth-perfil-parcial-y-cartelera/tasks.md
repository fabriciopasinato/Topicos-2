# Tasks

## 1. Perfil incompleto

- [x] 1.1 En `Perfil.jsx`, armar el `PATCH` solo con los campos que difieren de lo cargado (`piso_depto` vacío → `null`) y no llamar a la API si no hay cambios. Verificar en `Perfil.test.jsx`: un owner sin perfil que completa solo el teléfono manda `{"telefono": ...}` y ve "Datos guardados."; borrar un obligatorio que tenía valor manda `""` y muestra el 422 junto al campo; vaciar el piso sigue mandando `null`.
- [x] 1.2 Test de API en auth: un event owner creado por el admin (sin perfil) hace `PATCH /auth/perfil` con solo el teléfono, recibe 200 y el resto sigue vacío. Verificar con `pytest`.

## 2. Lecturas públicas con la sesión revocada

- [x] 2.1 En `client.js`, agregar `esLecturaPublica()` y, cuando falla el refresh en una lectura pública, borrar la sesión y repetir la solicitud sin token, sin llamar a `alFallarAuth`. Verificar en `SesionAuth.test.jsx`: la cartelera con una sesión revocada se muestra, no quedan tokens y el encabezado ofrece "Ingresar"; el detalle de un evento y su disponibilidad se muestran; "Mis eventos" lleva al login con el aviso; la lista de lecturas públicas queda fijada por un test.

## 3. Verificación

- [x] 3.1 Correr las suites de auth y gateway, `npm test` y `npm run build`, más `openspec validate auth-perfil-parcial-y-cartelera --strict`, todo en verde.
- [x] 3.2 Probar en el navegador con el stack levantado: el admin guarda solo su teléfono en "Mi perfil", y con una sesión revocada la cartelera se muestra sin pasar por el login.

## Workflow follow-up

- Archivar el change con `/opsx:archive`.
- El usuario commitea y pushea a `feature/auth-cuentas-y-perfil`; el PR #17 se actualiza solo.
