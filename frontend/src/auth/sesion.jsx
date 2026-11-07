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

export function SesionProvider({ children }) {
  const [usuario, setUsuario] = useState(() => {
    const t = tokensActuales();
    return t ? usuarioDeToken(t.access) : null;
  });

  useEffect(
    () => suscribirTokens((t) => setUsuario(t ? usuarioDeToken(t.access) : null)),
    [],
  );

  const valor = {
    usuario,
    async login(email, password) {
      guardarTokens(await api("/api/auth/login", { method: "POST", body: { email, password } }));
    },
    registrar(email, password) {
      return api("/api/auth/registro", { method: "POST", body: { email, password } });
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
