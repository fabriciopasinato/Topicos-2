import { useState } from "react";
import { Link } from "react-router-dom";
import { api, mensajeDeError } from "../../api/client.js";
import Campo from "../../components/Campo.jsx";
import Mensaje from "../../components/Mensaje.jsx";
import { erroresContrasenia } from "../../datos.js";

export default function AdminEventOwners() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errores, setErrores] = useState({});
  const [error, setError] = useState("");
  const [creado, setCreado] = useState("");

  const locales = erroresContrasenia(password, "");

  async function enviar(e) {
    e.preventDefault();
    if (locales.contrasenia) return;
    setError("");
    setErrores({});
    try {
      const owner = await api("/api/auth/event-owners", { method: "POST", body: { email, password } });
      setCreado(owner.email);
      setEmail("");
      setPassword("");
    } catch (err) {
      setErrores(err.errores ?? {});
      setError(mensajeDeError(err));
    }
  }

  return (
    <section className="tarjeta angosta">
      <p><Link to="/admin/usuarios">Volver al listado</Link></p>
      <h1>Alta de organizador</h1>
      <form onSubmit={enviar} noValidate>
        <Campo label="Email" nombre="email" type="email" value={email}
               onChange={(e) => setEmail(e.target.value)} error={errores.email} />
        <Campo label="Contraseña inicial" nombre="password" type="password" value={password}
               onChange={(e) => setPassword(e.target.value)} error={locales.contrasenia || errores.password} />
        <Mensaje>{error}</Mensaje>
        {creado && <Mensaje tipo="info">Organizador {creado} creado.</Mensaje>}
        <button type="submit" disabled={!email || !password || Boolean(locales.contrasenia)}>Crear organizador</button>
      </form>
    </section>
  );
}
