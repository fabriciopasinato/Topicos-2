import { useState } from "react";
import { api, mensajeDeError } from "../api/client.js";
import Campo from "../components/Campo.jsx";
import Mensaje from "../components/Mensaje.jsx";
import { useSesion } from "../auth/sesion.jsx";
import { erroresContrasenia } from "../datos.js";

export default function CambiarContrasenia() {
  const { renovarSesion } = useSesion();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetida, setRepetida] = useState("");
  const [errores, setErrores] = useState({});
  const [error, setError] = useState("");
  const [listo, setListo] = useState(false);

  const locales = erroresContrasenia(nueva, repetida);

  async function enviar(e) {
    e.preventDefault();
    if (Object.keys(locales).length) return;
    setError("");
    setErrores({});
    try {
      // El backend corta las demas sesiones y devuelve un par de tokens nuevo
      // para que esta siga abierta.
      renovarSesion(await api("/api/auth/perfil/contrasenia", { method: "POST", body: { actual, nueva } }));
      setListo(true);
      setActual("");
      setNueva("");
      setRepetida("");
    } catch (err) {
      if (err.status === 401) setErrores({ actual: "La contraseña actual no es correcta." });
      else {
        setErrores(err.errores ?? {});
        setError(mensajeDeError(err));
      }
    }
  }

  return (
    <section className="tarjeta angosta">
      <h1>Cambiar contraseña</h1>
      <form onSubmit={enviar} noValidate>
        <Campo label="Contraseña actual" nombre="actual" type="password" value={actual}
               onChange={(e) => setActual(e.target.value)} error={errores.actual} />
        <Campo label="Contraseña nueva" nombre="nueva" type="password" value={nueva}
               onChange={(e) => { setNueva(e.target.value); setListo(false); }}
               error={locales.contrasenia || errores.nueva} />
        <Campo label="Repetir contraseña nueva" nombre="repetida" type="password" value={repetida}
               onChange={(e) => setRepetida(e.target.value)} error={locales.repetida} />
        <Mensaje>{error}</Mensaje>
        {listo && (
          <Mensaje tipo="info">Contraseña actualizada. Se cerraron tus otras sesiones.</Mensaje>
        )}
        <button type="submit" disabled={!actual || !nueva || Object.keys(locales).length > 0}>
          Cambiar contraseña
        </button>
      </form>
    </section>
  );
}
