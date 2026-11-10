/**
 * Cliente de la API del gateway.
 *
 * - Agrega el token de acceso a cada solicitud.
 * - Ante un 401, renueva el token con el refresh token y reintenta UNA vez.
 *   Si la renovacion falla, borra la sesion y avisa (redirige al login).
 * - Los errores se lanzan como ApiError con status, detalle y Retry-After.
 */

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const CLAVE = "ticketera.tokens";

function leer() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE)) || null;
  } catch {
    return null;
  }
}

let tokens = leer();
let alFallarAuth = () => {};
let renovacionEnCurso = null;
const suscriptores = new Set();

export class ApiError extends Error {
  constructor(status, detail, retryAfter, codigo = null) {
    super(typeof detail === "string" ? detail : `Error ${status}`);
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
    // Codigo de negocio (por ejemplo "cuenta_bloqueada") para no parsear texto.
    this.codigo = codigo;
  }

  /** Errores de validacion por campo: { campo: "mensaje" }. */
  get errores() {
    if (!Array.isArray(this.detail)) return {};
    const porCampo = {};
    for (const e of this.detail) {
      const campo = e.loc?.[e.loc.length - 1];
      if (campo && !porCampo[campo]) porCampo[campo] = e.msg.replace(/^Value error, /, "");
    }
    return porCampo;
  }
}

export function tokensActuales() {
  return tokens;
}

/** `motivo` (opcional) explica por que se cerro la sesion, para avisarlo. */
export function guardarTokens(nuevos, motivo = null) {
  tokens = nuevos ? { access: nuevos.access_token, refresh: nuevos.refresh_token } : null;
  try {
    if (tokens) localStorage.setItem(CLAVE, JSON.stringify(tokens));
    else localStorage.removeItem(CLAVE);
  } catch {
    /* sin almacenamiento: la sesión dura lo que la pestaña */
  }
  suscriptores.forEach((fn) => fn(tokens, motivo));
}

export function borrarTokens(motivo = null) {
  guardarTokens(null, motivo);
}

export function suscribirTokens(fn) {
  suscriptores.add(fn);
  return () => suscriptores.delete(fn);
}

export function configurarAlFallarAuth(fn) {
  alFallarAuth = fn;
}

function enviar(ruta, { method = "GET", body, headers = {} }) {
  const final = { ...headers };
  if (body !== undefined) final["Content-Type"] = "application/json";
  if (tokens?.access) final.Authorization = `Bearer ${tokens.access}`;
  return fetch(`${API_URL}${ruta}`, {
    method,
    headers: final,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function renovar() {
  if (!tokens?.refresh) return false;
  // Varias solicitudes con 401 a la vez comparten una sola renovacion.
  renovacionEnCurso ??= (async () => {
    try {
      const r = await fetch(`${API_URL}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: tokens.refresh }),
      });
      if (!r.ok) return false;
      guardarTokens(await r.json());
      return true;
    } catch {
      return false;
    } finally {
      renovacionEnCurso = null;
    }
  })();
  return renovacionEnCurso;
}

export async function api(ruta, opciones = {}) {
  let r = await enviar(ruta, opciones);

  if (r.status === 401 && tokens?.refresh && !ruta.startsWith("/api/auth/")) {
    if (await renovar()) {
      r = await enviar(ruta, opciones);
    } else {
      // El motivo viaja con el cierre: las rutas protegidas redirigen al login
      // mostrando el aviso aunque se adelanten a la navegacion de alFallarAuth.
      borrarTokens("sesion_cerrada");
      alFallarAuth();
    }
  }

  if (!r.ok) {
    let cuerpo = {};
    try {
      cuerpo = await r.json();
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    const retry = r.headers.get("Retry-After");
    throw new ApiError(r.status, cuerpo.detail ?? null, retry ? Number(retry) : null, cuerpo.codigo ?? null);
  }
  return r.status === 204 ? null : r.json();
}

/** Mensaje para mostrar al usuario segun el error. */
export function mensajeDeError(error, porStatus = {}) {
  if (!(error instanceof ApiError)) return "No se pudo conectar con el servidor.";
  if (error.status === 429) {
    return `Demasiados intentos. Probá de nuevo en ${error.retryAfter ?? 60} segundos.`;
  }
  if (porStatus[error.status]) return porStatus[error.status];
  if (typeof error.detail === "string") return error.detail;
  if (error.status === 422) return "Revisá los datos marcados.";
  return `Error ${error.status}`;
}
