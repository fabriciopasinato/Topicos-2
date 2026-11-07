import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";

export function formatearFecha(iso) {
  return new Date(iso).toLocaleString("es-AR", { dateStyle: "long", timeStyle: "short" });
}

export default function Cartelera() {
  const [eventos, setEventos] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/eventos").then(setEventos).catch((e) => setError(mensajeDeError(e)));
  }, []);

  if (error) return <Mensaje>{error}</Mensaje>;
  if (!eventos) return <p>Cargando cartelera…</p>;

  return (
    <section>
      <h1>Cartelera</h1>
      {eventos.length === 0 ? (
        <p>No hay eventos publicados por ahora.</p>
      ) : (
        <ul className="grilla-eventos">
          {eventos.map((e) => (
            <li key={e.id} className="tarjeta">
              <h2>
                <Link to={`/eventos/${e.id}`}>{e.nombre}</Link>
              </h2>
              <p>{formatearFecha(e.fecha)}</p>
              <p className="tenue">{e.recinto.nombre}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
