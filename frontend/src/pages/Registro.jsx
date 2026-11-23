import { useState } from "react";
import { Link } from "react-router-dom";
import { mensajeDeError } from "../api/client.js";
import Campo from "../components/Campo.jsx";
import Mensaje from "../components/Mensaje.jsx";
import { useSesion } from "../auth/sesion.jsx";
import { erroresContrasenia, PROVINCIAS } from "../datos.js";

const VACIO = {
  nombre: "", apellido: "", dni: "", fecha_nacimiento: "", telefono: "",
  calle: "", numero: "", piso_depto: "", localidad: "", provincia: "", codigo_postal: "",
  email: "", password: "", repetida: "",
};

/** Validacion local: feedback inmediato. El backend vuelve a validar todo. */
function erroresLocales(d) {
  const errores = {};
  if (d.dni && !/^\d{7,8}$/.test(d.dni)) errores.dni = "El DNI son 7 u 8 números, sin puntos.";
  const c = erroresContrasenia(d.password, d.repetida);
  if (c.contrasenia) errores.password = c.contrasenia;
  if (c.repetida) errores.repetida = c.repetida;
  return errores;
}

export default function Registro() {
  const { registrar } = useSesion();
  const [datos, setDatos] = useState(VACIO);
  const [erroresServidor, setErroresServidor] = useState({});
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [registrado, setRegistrado] = useState(null);

  const locales = erroresLocales(datos);
  const errores = { ...erroresServidor, ...locales };

  function cambiar(e) {
    const { name, value } = e.target;
    setDatos((d) => ({ ...d, [name]: value }));
    setErroresServidor((prev) => ({ ...prev, [name]: undefined }));
  }

  function campo(nombre, label, props = {}) {
    return (
      <Campo label={label} nombre={nombre} value={datos[nombre]} onChange={cambiar}
             error={errores[nombre]} {...props} />
    );
  }

  async function enviar(e) {
    e.preventDefault();
    if (Object.keys(locales).length) return;
    setError("");
    setEnviando(true);
    const { repetida, piso_depto, ...resto } = datos;
    try {
      await registrar({ ...resto, piso_depto: piso_depto || null });
      setRegistrado(datos.email);
    } catch (err) {
      setErroresServidor(err.errores ?? {});
      setError(mensajeDeError(err));
    } finally {
      setEnviando(false);
    }
  }

  if (registrado) {
    return (
      <section className="tarjeta angosta">
        <h1>¡Ya casi!</h1>
        <p role="status">
          Te enviamos un email a <strong>{registrado}</strong> para verificar tu cuenta. Entrá al link
          para activarla.
        </p>
        <Link to="/login">Ir a ingresar</Link>
      </section>
    );
  }

  return (
    <section className="tarjeta">
      <h1>Crear cuenta</h1>
      <form onSubmit={enviar} noValidate>
        <fieldset>
          <legend>Datos personales</legend>
          <div className="grilla-campos">
            {campo("nombre", "Nombre", { required: true })}
            {campo("apellido", "Apellido", { required: true })}
            {campo("dni", "DNI", { required: true, inputMode: "numeric" })}
            {campo("fecha_nacimiento", "Fecha de nacimiento", { type: "date", required: true })}
            {campo("telefono", "Teléfono", { type: "tel", required: true })}
          </div>
        </fieldset>

        <fieldset>
          <legend>Dirección</legend>
          <div className="grilla-campos">
            {campo("calle", "Calle", { required: true })}
            {campo("numero", "Número", { required: true })}
            {campo("piso_depto", "Piso / depto (opcional)")}
            {campo("localidad", "Localidad", { required: true })}
            <Campo label="Provincia" nombre="provincia" error={errores.provincia}>
              <select name="provincia" value={datos.provincia} onChange={cambiar} required
                      aria-invalid={Boolean(errores.provincia)}>
                <option value="">Elegí una provincia</option>
                {PROVINCIAS.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </Campo>
            {campo("codigo_postal", "Código postal", { required: true })}
          </div>
        </fieldset>

        <fieldset>
          <legend>Cuenta</legend>
          <div className="grilla-campos">
            {campo("email", "Email", { type: "email", required: true })}
            {campo("password", "Contraseña", { type: "password", required: true, minLength: 10 })}
            {campo("repetida", "Repetir contraseña", { type: "password", required: true })}
          </div>
          <p className="tenue">Al menos 10 caracteres. Una frase larga es más segura que símbolos raros.</p>
        </fieldset>

        <Mensaje>{error}</Mensaje>
        <button type="submit" disabled={enviando || Object.keys(locales).length > 0}>
          Registrarme
        </button>
      </form>
      <p>
        ¿Ya tenés cuenta? <Link to="/login">Ingresá</Link>
      </p>
    </section>
  );
}
