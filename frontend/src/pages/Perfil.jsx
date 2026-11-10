import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mensajeDeError } from "../api/client.js";
import Campo from "../components/Campo.jsx";
import Mensaje from "../components/Mensaje.jsx";
import { formatearFechaHora, PROVINCIAS } from "../datos.js";

const EDITABLES = [
  "nombre", "apellido", "fecha_nacimiento", "telefono",
  "calle", "numero", "piso_depto", "localidad", "provincia", "codigo_postal",
];

export default function Perfil() {
  const [perfil, setPerfil] = useState(null);
  const [datos, setDatos] = useState({});
  const [errores, setErrores] = useState({});
  const [error, setError] = useState("");
  const [guardado, setGuardado] = useState("");

  function cargar(p) {
    setPerfil(p);
    setDatos(Object.fromEntries(EDITABLES.map((c) => [c, p[c] ?? ""])));
  }

  useEffect(() => {
    api("/api/auth/perfil").then(cargar).catch((e) => setError(mensajeDeError(e)));
  }, []);

  function cambiar(e) {
    setDatos((d) => ({ ...d, [e.target.name]: e.target.value }));
    setGuardado("");
  }

  async function guardar(e) {
    e.preventDefault();
    setError("");
    setErrores({});
    try {
      const cuerpo = Object.fromEntries(EDITABLES.map((c) => [c, datos[c] === "" ? null : datos[c]]));
      cargar(await api("/api/auth/perfil", { method: "PATCH", body: cuerpo }));
      setGuardado("Datos guardados.");
    } catch (err) {
      setErrores(err.errores ?? {});
      setError(mensajeDeError(err));
    }
  }

  if (!perfil) return error ? <Mensaje>{error}</Mensaje> : <p>Cargando perfil…</p>;

  const campo = (nombre, label, props = {}) => (
    <Campo label={label} nombre={nombre} value={datos[nombre]} onChange={cambiar} error={errores[nombre]} {...props} />
  );

  return (
    <section className="tarjeta">
      <h1>Mi perfil</h1>
      <dl className="datos-fijos">
        <dt>Email</dt><dd>{perfil.email}</dd>
        <dt>DNI</dt><dd>{perfil.dni ?? "-"}</dd>
        <dt>Cuenta creada</dt><dd>{formatearFechaHora(perfil.created_at)}</dd>
        <dt>Última modificación</dt><dd>{formatearFechaHora(perfil.updated_at)}</dd>
        <dt>Último ingreso</dt><dd>{formatearFechaHora(perfil.last_login_at)}</dd>
      </dl>

      <form onSubmit={guardar} noValidate>
        <div className="grilla-campos">
          {campo("nombre", "Nombre")}
          {campo("apellido", "Apellido")}
          {campo("fecha_nacimiento", "Fecha de nacimiento", { type: "date" })}
          {campo("telefono", "Teléfono", { type: "tel" })}
          {campo("calle", "Calle")}
          {campo("numero", "Número")}
          {campo("piso_depto", "Piso / depto")}
          {campo("localidad", "Localidad")}
          <Campo label="Provincia" nombre="provincia" error={errores.provincia}>
            <select name="provincia" value={datos.provincia} onChange={cambiar}>
              <option value="">-</option>
              {PROVINCIAS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </Campo>
          {campo("codigo_postal", "Código postal")}
        </div>
        <Mensaje>{error}</Mensaje>
        <Mensaje tipo="info">{guardado}</Mensaje>
        <div className="acciones">
          <button type="submit">Guardar cambios</button>
          <Link to="/perfil/contrasenia">Cambiar contraseña</Link>
        </div>
      </form>
    </section>
  );
}
