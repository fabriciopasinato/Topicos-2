import { useState } from "react";
import { Link } from "react-router-dom";
import { api, mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";

export default function Olvide() {
  const [email, setEmail] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [error, setError] = useState("");

  async function enviar(e) {
    e.preventDefault();
    setError("");
    try {
      await api("/api/auth/olvide-contrasenia", { method: "POST", body: { email } });
      setEnviado(true);
    } catch (err) {
      setError(mensajeDeError(err));
    }
  }

  if (enviado) {
    return (
      <section className="tarjeta angosta">
        <h1>Revisá tu email</h1>
        {/* Mismo mensaje exista o no la cuenta: no revela que emails estan registrados. */}
        <p role="status">
          Si <strong>{email}</strong> está registrado, te enviamos un link para crear una contraseña nueva.
          Vence en 30 minutos.
        </p>
        <Link to="/login">Volver a ingresar</Link>
      </section>
    );
  }

  return (
    <section className="tarjeta angosta">
      <h1>Olvidé mi contraseña</h1>
      <form onSubmit={enviar}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <Mensaje>{error}</Mensaje>
        <button type="submit">Enviarme el link</button>
      </form>
    </section>
  );
}
