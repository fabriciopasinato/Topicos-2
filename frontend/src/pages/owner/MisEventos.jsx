import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mensajeDeError } from "../../api/client.js";
import Mensaje from "../../components/Mensaje.jsx";
import { formatearFecha } from "../Cartelera.jsx";
import { NOMBRE_ESTADO, textoPendiente } from "./comun.js";

export default function MisEventos() {
  const [eventos, setEventos] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/eventos/mios").then(setEventos).catch((e) => setError(mensajeDeError(e)));
  }, []);

  if (error) return <Mensaje>{error}</Mensaje>;
  if (!eventos) return <p>Cargando tus eventos…</p>;

  return (
    <section>
      <h1>Mis eventos</h1>
      <p>
        <Link to="/owner/eventos/nuevo">Crear evento</Link>
      </p>
      {eventos.length === 0 ? (
        <p>Todavía no creaste eventos.</p>
      ) : (
        <ul className="lista">
          {eventos.map((e) => (
            <li key={e.id} className="tarjeta">
              <h2>
                <Link to={`/owner/eventos/${e.id}`}>{e.nombre}</Link>{" "}
                <span className="estado">{NOMBRE_ESTADO[e.estado] ?? e.estado}</span>
              </h2>
              <p>
                {formatearFecha(e.fecha)} · {e.recinto.nombre}
              </p>
              {e.operaciones_pendientes.map((op, i) => (
                <Mensaje key={i} tipo="info">
                  {textoPendiente(op)}
                </Mensaje>
              ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
