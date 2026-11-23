import { ApiError, mensajeDeError } from "../../api/client.js";

export const NOMBRE_ESTADO = {
  borrador: "Borrador",
  publicado: "Publicado",
  finalizado: "Finalizado",
  cancelado: "Cancelado",
};

// Espejo de ACCIONES_PERMITIDAS del backend: solo decide que botones mostrar;
// la regla la aplica el backend igual (409).
export const ACCIONES = {
  borrador: ["editar", "cambiar_recinto", "zonas", "publicar", "reprogramar", "cancelar", "borrar"],
  publicado: ["editar", "reprogramar", "cancelar"],
  finalizado: [],
  cancelado: [],
};

export function puede(evento, accion) {
  return (ACCIONES[evento.estado] ?? []).includes(accion);
}

export function textoPendiente(op) {
  return op.tipo === "cancelar"
    ? "Cancelación en proceso: se completará cuando ventas esté disponible."
    : "Reprogramación en proceso: se completará cuando ventas esté disponible.";
}

/** El detalle del backend si es texto (409/422 de negocio); si no, el mensaje por defecto. */
export function mensaje(error, porDefecto) {
  if (error instanceof ApiError && typeof error.detail === "string" && error.status !== 429) return error.detail;
  return error instanceof ApiError && error.status !== 429 ? porDefecto : mensajeDeError(error);
}

/** "2030-01-10T21:00" (input datetime-local) -> ISO con zona horaria. */
export function aIso(local) {
  return new Date(local).toISOString();
}
