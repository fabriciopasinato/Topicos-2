import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";
import { useSesion } from "../auth/sesion.jsx";

export default function Registro() {
  const { registrar } = useSesion();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      await registrar(email, password);
      navigate("/login", { state: { aviso: "Cuenta creada. Ya podés ingresar." } });
    } catch (err) {
      setError(
        mensajeDeError(err, {
          409: "Ese email ya está registrado.",
          422: "Revisá los datos: email válido y contraseña de al menos 8 caracteres.",
        }),
      );
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="tarjeta angosta">
      <h1>Crear cuenta</h1>
      <form onSubmit={enviar}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Contraseña
          <input type="password" value={password} minLength={8}
                 onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <Mensaje>{error}</Mensaje>
        <button type="submit" disabled={enviando}>Registrarme</button>
      </form>
      <p>
        ¿Ya tenés cuenta? <Link to="/login">Ingresá</Link>
      </p>
    </section>
  );
}
