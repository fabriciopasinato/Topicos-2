import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";
import { useSesion } from "../auth/sesion.jsx";

export default function Login() {
  const { login } = useSesion();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      await login(email, password);
      navigate(location.state?.volverA || "/", { replace: true });
    } catch (err) {
      setError(mensajeDeError(err, { 401: "Email o contraseña incorrectos." }));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="tarjeta angosta">
      <h1>Ingresar</h1>
      <Mensaje tipo="info">{location.state?.aviso}</Mensaje>
      <form onSubmit={enviar}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Contraseña
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <Mensaje>{error}</Mensaje>
        <button type="submit" disabled={enviando}>Ingresar</button>
      </form>
      <p>
        ¿No tenés cuenta? <Link to="/registro">Registrate</Link>
      </p>
    </section>
  );
}
