import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";

export function formatearFecha(iso) {
  return new Date(iso).toLocaleString("es-AR", { dateStyle: "long", timeStyle: "short" });
}

export function Clasificacion({ evento, tipos }) {
  const tipo = tipos.find((t) => t.codigo === evento.tipo)?.nombre ?? evento.tipo;
  return (
    <p className="tenue">
      {tipo}
      {evento.organizador && ` · ${evento.organizador.nombre}`}
      {evento.participantes?.length > 0 && ` · ${evento.participantes.map((p) => p.nombre).join(", ")}`}
    </p>
  );
}

/** "2030-01-10" (input date) -> ISO del inicio o del fin de ese dia, en hora local. */
function limiteDelDia(fecha, fin) {
  return new Date(`${fecha}T${fin ? "23:59:59" : "00:00:00"}`).toISOString();
}

export default function Cartelera() {
  const [eventos, setEventos] = useState(null);
  const [tipos, setTipos] = useState([]);
  const [filtros, setFiltros] = useState({ tipo: "", desde: "", hasta: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/eventos/tipos").then(setTipos).catch(() => setTipos([]));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (filtros.tipo) params.set("tipo", filtros.tipo);
    if (filtros.desde) params.set("desde", limiteDelDia(filtros.desde, false));
    if (filtros.hasta) params.set("hasta", limiteDelDia(filtros.hasta, true));
    const consulta = params.toString();
    setError("");
    api(`/api/eventos${consulta ? `?${consulta}` : ""}`)
      .then(setEventos)
      .catch((e) => setError(mensajeDeError(e, { 422: "Revisá los filtros: el rango de fechas no es válido." })));
  }, [filtros]);

  const cambiar = (campo) => (e) => setFiltros((f) => ({ ...f, [campo]: e.target.value }));

  return (
    <section>
      <h1>Cartelera</h1>
      <div className="filtros">
        <label>
          Tipo
          <select value={filtros.tipo} onChange={cambiar("tipo")}>
            <option value="">Todos</option>
            {tipos.map((t) => (
              <option key={t.codigo} value={t.codigo}>
                {t.nombre}
              </option>
            ))}
          </select>
        </label>
        <label>
          Desde
          <input type="date" value={filtros.desde} onChange={cambiar("desde")} />
        </label>
        <label>
          Hasta
          <input type="date" value={filtros.hasta} onChange={cambiar("hasta")} />
        </label>
      </div>
      <Mensaje>{error}</Mensaje>
      {!eventos && !error && <p>Cargando cartelera…</p>}
      {eventos && eventos.length === 0 && <p>No hay eventos publicados por ahora.</p>}
      {eventos && eventos.length > 0 && (
        <ul className="grilla-eventos">
          {eventos.map((e) => (
            <li key={e.id} className="tarjeta">
              <h2>
                <Link to={`/eventos/${e.id}`}>{e.nombre}</Link>
              </h2>
              <p>{formatearFecha(e.fecha)}</p>
              <p className="tenue">{e.recinto.nombre}</p>
              <Clasificacion evento={e} tipos={tipos} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
