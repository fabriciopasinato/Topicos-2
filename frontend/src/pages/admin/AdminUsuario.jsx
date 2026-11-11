import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, mensajeDeError } from "../../api/client.js";
import Mensaje from "../../components/Mensaje.jsx";
import { formatearFechaHora } from "../../datos.js";

const MOTIVOS = {
  intentos_fallidos: "Bloqueada por intentos fallidos",
  restablecimiento_admin: "Contraseña restablecida por un administrador",
};

export default function AdminUsuario() {
  const { id } = useParams();
  const [cuenta, setCuenta] = useState(null);
  const [error, setError] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [aviso, setAviso] = useState("");

  function cargar() {
    api(`/api/auth/admin/usuarios/${id}`)
      .then(setCuenta)
      .catch((e) => setError(mensajeDeError(e, { 404: "La cuenta no existe." })));
  }

  useEffect(cargar, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function restablecer() {
    setConfirmando(false);
    try {
      await api(`/api/auth/admin/usuarios/${id}/restablecer-contrasenia`, { method: "POST" });
      setAviso("Listo: se cerraron sus sesiones y le enviamos un email para crear una contraseña nueva.");
      cargar();
    } catch (e) {
      setError(mensajeDeError(e));
    }
  }

  if (!cuenta) return error ? <Mensaje>{error}</Mensaje> : <p>Cargando cuenta…</p>;

  const direccion = [cuenta.calle, cuenta.numero, cuenta.piso_depto].filter(Boolean).join(" ");

  return (
    <section className="tarjeta">
      <p><Link to="/admin/usuarios">Volver al listado</Link></p>
      <h1>{cuenta.email}</h1>
      <dl className="datos-fijos">
        <dt>Nombre</dt><dd>{[cuenta.nombre, cuenta.apellido].filter(Boolean).join(" ") || "-"}</dd>
        <dt>DNI</dt><dd>{cuenta.dni ?? "-"}</dd>
        <dt>Rol</dt><dd>{cuenta.rol}</dd>
        <dt>Estado</dt>
        <dd>{cuenta.estado}{cuenta.motivo_bloqueo ? ` (${MOTIVOS[cuenta.motivo_bloqueo]})` : ""}</dd>
        <dt>Intentos fallidos</dt><dd>{cuenta.intentos_fallidos}</dd>
        <dt>Dirección</dt>
        <dd>{direccion ? `${direccion}, ${cuenta.localidad}, ${cuenta.provincia} (${cuenta.codigo_postal})` : "-"}</dd>
        <dt>Teléfono</dt><dd>{cuenta.telefono ?? "-"}</dd>
        <dt>Creada</dt><dd>{formatearFechaHora(cuenta.created_at)}</dd>
        <dt>Última modificación</dt><dd>{formatearFechaHora(cuenta.updated_at)}</dd>
        <dt>Último ingreso</dt><dd>{formatearFechaHora(cuenta.last_login_at)}</dd>
      </dl>

      <Mensaje>{error}</Mensaje>
      <Mensaje tipo="info">{aviso}</Mensaje>
      {confirmando ? (
        <div className="acciones">
          <span>¿Restablecer la contraseña? El usuario no va a poder ingresar hasta crear una nueva.</span>
          <button type="button" onClick={restablecer}>Sí, restablecer</button>
          <button type="button" className="secundario" onClick={() => setConfirmando(false)}>Cancelar</button>
        </div>
      ) : (
        <button type="button" onClick={() => setConfirmando(true)}>Restablecer contraseña</button>
      )}
    </section>
  );
}
