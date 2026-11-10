import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, mensajeDeError } from "../api/client.js";
import Campo from "../components/Campo.jsx";
import Mensaje from "../components/Mensaje.jsx";
import { erroresContrasenia } from "../datos.js";

export default function Restablecer() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [contrasenia, setContrasenia] = useState("");
  const [repetida, setRepetida] = useState("");
  const [errorServidor, setErrorServidor] = useState("");
  const [vencido, setVencido] = useState(!token);
  const [error, setError] = useState("");

  const locales = erroresContrasenia(contrasenia, repetida);

  async function enviar(e) {
    e.preventDefault();
    if (Object.keys(locales).length) return;
    setError("");
    setErrorServidor("");
    try {
      await api("/api/auth/restablecer-contrasenia", { method: "POST", body: { token, contrasenia } });
      navigate("/login", { state: { aviso: "Contraseña actualizada. Ya podés ingresar." } });
    } catch (err) {
      if (err.status === 400) setVencido(true);
      else if (err.errores?.contrasenia) setErrorServidor(err.errores.contrasenia);
      else setError(mensajeDeError(err));
    }
  }

  if (vencido) {
    return (
      <section className="tarjeta angosta">
        <h1>El link no es válido</h1>
        <p role="alert">El link venció o ya se usó. Pedí uno nuevo.</p>
        <Link to="/olvide">Pedir otro link</Link>
      </section>
    );
  }

  return (
    <section className="tarjeta angosta">
      <h1>Nueva contraseña</h1>
      <form onSubmit={enviar} noValidate>
        <Campo label="Contraseña nueva" nombre="contrasenia" type="password" value={contrasenia}
               onChange={(e) => setContrasenia(e.target.value)} error={locales.contrasenia || errorServidor} />
        <Campo label="Repetir contraseña" nombre="repetida" type="password" value={repetida}
               onChange={(e) => setRepetida(e.target.value)} error={locales.repetida} />
        <Mensaje>{error}</Mensaje>
        <button type="submit" disabled={!contrasenia || Object.keys(locales).length > 0}>
          Guardar contraseña
        </button>
      </form>
    </section>
  );
}
