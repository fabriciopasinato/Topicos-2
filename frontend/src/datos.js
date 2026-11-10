/** Las 24 jurisdicciones (mismos valores que valida auth). */
export const PROVINCIAS = [
  "Buenos Aires", "Ciudad Autónoma de Buenos Aires", "Catamarca", "Chaco", "Chubut", "Córdoba",
  "Corrientes", "Entre Ríos", "Formosa", "Jujuy", "La Pampa", "La Rioja", "Mendoza", "Misiones",
  "Neuquén", "Río Negro", "Salta", "San Juan", "San Luis", "Santa Cruz", "Santa Fe",
  "Santiago del Estero", "Tierra del Fuego", "Tucumán",
];

export const CONTRASENIA_MIN = 10;
export const CONTRASENIA_MAX = 128;

/** Validacion local de la contrasenia (el backend vuelve a validar todo). */
export function erroresContrasenia(contrasenia, repetida) {
  const errores = {};
  if (contrasenia && contrasenia.length < CONTRASENIA_MIN) {
    errores.contrasenia = `Mínimo ${CONTRASENIA_MIN} caracteres.`;
  } else if (contrasenia.length > CONTRASENIA_MAX) {
    errores.contrasenia = `Máximo ${CONTRASENIA_MAX} caracteres.`;
  }
  if (repetida && contrasenia !== repetida) errores.repetida = "Las contraseñas no coinciden.";
  return errores;
}

export function formatearFechaHora(iso) {
  return iso ? new Date(iso).toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" }) : "Nunca";
}
