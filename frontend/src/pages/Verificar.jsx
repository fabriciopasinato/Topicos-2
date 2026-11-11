import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client.js";

export default function Verificar() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [estado, setEstado] = useState(token ? "verificando" : "invalido");
  // El token es de un solo uso: en desarrollo StrictMode ejecuta los efectos
  // dos veces, y la segunda llamada lo encontraria ya usado.
  const enviado = useRef(false);

  useEffect(() => {
    if (!token || enviado.current) return;
    enviado.current = true;
    api("/api/auth/verificar-email", { method: "POST", body: { token } })
      .then(() => setEstado("ok"))
      .catch(() => setEstado("invalido"));
  }, [token]);

  return (
    <section className="tarjeta angosta">
      {estado === "verificando" && <p>Verificando tu cuenta…</p>}
      {estado === "ok" && (
        <>
          <h1>¡Cuenta verificada!</h1>
          <p role="status">Ya podés ingresar con tu email y contraseña.</p>
          <Link to="/login">Ingresar</Link>
        </>
      )}
      {estado === "invalido" && (
        <>
          <h1>El link no es válido</h1>
          <p role="alert">El link venció o ya se usó. Ingresá con tu email y te ofrecemos reenviarlo.</p>
          <Link to="/login">Ir a ingresar</Link>
        </>
      )}
    </section>
  );
}
