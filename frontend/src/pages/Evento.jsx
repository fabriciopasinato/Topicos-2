import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";
import { useSesion } from "../auth/sesion.jsx";
import { formatearFecha } from "./Cartelera.jsx";

function nuevaClave() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Une la definición (eventos) con la disponibilidad (ventas) por zona_id. */
function unirZonas(evento, disponibilidad) {
  const porZona = Object.fromEntries(disponibilidad.zonas.map((z) => [z.zona_id, z]));
  return evento.sectores.flatMap((s) =>
    s.zonas.map((z) => ({
      ...z,
      sector: s.nombre,
      disp: porZona[z.id] ?? { disponibles: 0, asientos: [] },
    })),
  );
}

function MapaDeAsientos({ zona, seleccion, alternar }) {
  const filas = useMemo(() => {
    const agrupado = {};
    for (const a of zona.disp.asientos) (agrupado[a.fila] ??= []).push(a);
    return Object.entries(agrupado);
  }, [zona]);

  return (
    <div className="mapa" aria-label={`Asientos de ${zona.nombre}`}>
      {filas.map(([fila, asientos]) => (
        <div key={fila} className="fila">
          <span className="nombre-fila">{fila}</span>
          {asientos.map((a) => {
            const elegido = seleccion.has(a.ticket_id);
            return (
              <button
                key={a.ticket_id}
                type="button"
                className={`asiento ${elegido ? "elegido" : ""}`}
                disabled={!a.disponible}
                aria-pressed={elegido}
                aria-label={`Asiento ${a.fila}-${a.numero}${a.disponible ? "" : " no disponible"}`}
                onClick={() => alternar(a.ticket_id)}
              >
                {a.numero}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export default function Evento() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { usuario } = useSesion();
  const [evento, setEvento] = useState(null);
  const [zonas, setZonas] = useState([]);
  const [asientos, setAsientos] = useState(new Set());
  const [cantidades, setCantidades] = useState({});
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);
  // Una clave por intento de reserva: se reutiliza en los reintentos y se
  // renueva cuando cambia la selección.
  const clave = useRef(nuevaClave());

  const cargar = useCallback(async () => {
    try {
      const [ev, disp] = await Promise.all([
        api(`/api/eventos/${id}`),
        api(`/api/ventas/eventos/${id}/disponibilidad`),
      ]);
      setEvento(ev);
      setZonas(unirZonas(ev, disp));
    } catch (e) {
      setError(mensajeDeError(e, { 404: "El evento no existe." }));
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function cambioSeleccion(fn) {
    clave.current = nuevaClave();
    setError("");
    fn();
  }

  function alternar(ticketId) {
    cambioSeleccion(() =>
      setAsientos((prev) => {
        const nueva = new Set(prev);
        if (nueva.has(ticketId)) nueva.delete(ticketId);
        else nueva.add(ticketId);
        return nueva;
      }),
    );
  }

  const generales = Object.entries(cantidades)
    .filter(([, c]) => c > 0)
    .map(([zonaId, cantidad]) => ({ zona_id: Number(zonaId), cantidad }));
  const total = asientos.size + generales.reduce((s, g) => s + g.cantidad, 0);

  async function reservar() {
    if (!usuario) {
      navigate("/login", { state: { volverA: `/eventos/${id}`, aviso: "Ingresá para reservar." } });
      return;
    }
    setEnviando(true);
    setError("");
    try {
      const reserva = await api("/api/ventas/reservas", {
        method: "POST",
        body: { evento_id: Number(id), asientos: [...asientos], generales },
        headers: { "Idempotency-Key": clave.current },
      });
      navigate(`/reservas/${reserva.id}`);
    } catch (e) {
      setError(mensajeDeError(e, { 403: "Solo los clientes pueden comprar entradas." }));
      if (e.status === 409) {
        // Otro comprador los tomó: se refresca la disponibilidad y se limpia la selección.
        clave.current = nuevaClave();
        setAsientos(new Set());
        setCantidades({});
        cargar();
      }
    } finally {
      setEnviando(false);
    }
  }

  if (!evento) return error ? <Mensaje>{error}</Mensaje> : <p>Cargando evento…</p>;

  return (
    <section>
      <h1>{evento.nombre}</h1>
      <p>
        {formatearFecha(evento.fecha)} · {evento.recinto.nombre}
      </p>

      {zonas.map((z) => (
        <article key={z.id} className="tarjeta">
          <h2>
            {z.sector} · {z.nombre}
          </h2>
          <p className="tenue">
            ${z.precio} por entrada · {z.disp.disponibles} disponibles
          </p>
          {z.tipo === "numerada" ? (
            <MapaDeAsientos zona={z} seleccion={asientos} alternar={alternar} />
          ) : (
            <label>
              Cantidad para {z.nombre}
              <input
                type="number"
                min="0"
                max={z.disp.disponibles}
                value={cantidades[z.id] ?? 0}
                onChange={(e) => {
                  const valor = Math.max(0, Number(e.target.value) || 0);
                  cambioSeleccion(() => setCantidades((prev) => ({ ...prev, [z.id]: valor })));
                }}
              />
            </label>
          )}
        </article>
      ))}

      <Mensaje>{error}</Mensaje>
      <button type="button" disabled={total === 0 || enviando} onClick={reservar}>
        Reservar{total > 0 ? ` (${total})` : ""}
      </button>
    </section>
  );
}
