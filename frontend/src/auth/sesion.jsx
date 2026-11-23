import { createContext, useContext, useEffect, useState } from "react";
import { api, borrarTokens, guardarTokens, suscribirTokens, tokensActuales } from "../api/client.js";

/** Lee sub y rol del token de acceso (sin verificar: eso lo hace el gateway). */
export function usuarioDeToken(token) {
  try {
    const parte = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const datos = JSON.parse(atob(parte));
    return { id: Number(datos.sub), rol: datos.rol };
  } catch {
    return null;
  }
}

const SesionContext = createContext(null);

export const AVISO_SESION_CERRADA = "Tu sesión se cerró. Volvé a ingresar.";

export function SesionProvider({ children }) {
  const [usuario, setUsuario] = useState(() => {
    const t = tokensActuales();
    return t ? usuarioDeToken(t.access) : null;
  });

  // Aviso a mostrar en el login cuando el servidor cerro la sesion (revocada o vencida).
  const [avisoCierre, setAvisoCierre] = useState(null);

  useEffect(
    () =>
      suscribirTokens((t, motivo) => {
        setUsuario(t ? usuarioDeToken(t.access) : null);
        setAvisoCierre(!t && motivo === "sesion_cerrada" ? AVISO_SESION_CERRADA : null);
      }),
    [],
  );

  const valor = {
    usuario,
    avisoCierre,
    async login(email, password) {
      guardarTokens(await api("/api/auth/login", { method: "POST", body: { email, password } }));
    },
    registrar(datos) {
      return api("/api/auth/registro", { method: "POST", body: datos });
    },
    /** Guarda el par de tokens nuevo (por ejemplo, tras cambiar la contrasenia). */
    renovarSesion(tokens) {
      guardarTokens(tokens);
    },
    logout() {
      borrarTokens();
    },
  };
  return <SesionContext.Provider value={valor}>{children}</SesionContext.Provider>;
}

export function useSesion() {
  return useContext(SesionContext);
}
