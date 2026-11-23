import { useCallback, useEffect, useRef, useState } from "react";
import { api, mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";
import { formatearFecha } from "./Cartelera.jsx";

export default function AdminDevoluciones() {
  const [estado, setEstado] = useState("pendiente");
  const [devoluciones, setDevoluciones] = useState(null);
  const [notas, setNotas] = useState({});
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [procesando, setProcesando] = useState(() => new Set());

  const estadoRef = useRef(estado);
  estadoRef.current = estado;
  const reqIdRef = useRef(0);
  const montadoRef = useRef(true);
  const enCursoRef = useRef(new Set());

  useEffect(() => {
    montadoRef.current = true;
    return () => {
      montadoRef.current = false;
    };
  }, []);

  const cargar = useCallback(async (filtro) => {
    const estadoActual = filtro !== undefined ? filtro : estadoRef.current;
    const reqId = ++reqIdRef.current;
    setError("");
    try {
      const qs = estadoActual ? `?estado=${encodeURIComponent(estadoActual)}` : "";
      const datos = await api(`/api/ventas/devoluciones${qs}`);
      if (montadoRef.current && reqId === reqIdRef.current) {
        setDevoluciones(datos);
      }
    } catch (e) {
      if (montadoRef.current && reqId === reqIdRef.current) {
        setError(mensajeDeError(e));
      }
    }
  }, []);

  useEffect(() => {
    cargar(estado);
  }, [estado, cargar]);

  async function resolver(id, accion) {
    if (enCursoRef.current.has(id)) return;
    enCursoRef.current.add(id);
    setProcesando(new Set(enCursoRef.current));
    setError("");
    setAviso("");
    try {
      const nota = (notas[id] ?? "").trim() || null;
      await api(`/api/ventas/devoluciones/${id}/${accion}`, {
        method: "POST",
        body: { nota },
      });
      if (!montadoRef.current) return;
      setNotas((prev) => {
        const copia = { ...prev };
        delete copia[id];
        return copia;
      });
      setAviso(accion === "aprobar" ? `Devolución #${id} aprobada.` : `Devolución #${id} rechazada.`);
      await cargar();
    } catch (e) {
      if (montadoRef.current) {
        setError(mensajeDeError(e));
      }
    } finally {
      enCursoRef.current.delete(id);
      if (montadoRef.current) {
        setProcesando(new Set(enCursoRef.current));
      }
    }
  }

  return (
    <section>
      <h1>Gestión de devoluciones</h1>
      <label>
        Filtrar por estado
        <select value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="pendiente">Pendientes</option>
          <option value="aprobada">Aprobadas</option>
          <option value="rechazada">Rechazadas</option>
          <option value="">Todas</option>
        </select>
      </label>

      <Mensaje tipo="info">{aviso}</Mensaje>
      <Mensaje>{error}</Mensaje>

      {!devoluciones ? (
        <p>Cargando devoluciones…</p>
      ) : devoluciones.length === 0 ? (
        <p>No hay solicitudes de devolución para el filtro seleccionado.</p>
      ) : (
        <ul className="lista">
          {devoluciones.map((d) => (
            <li key={d.id} className="tarjeta">
              <h2>
                Solicitud #{d.id} · {d.estado}
              </h2>
              <p>
                {d.fila ? `Asiento ${d.fila}-${d.numero}` : "Entrada general"} · ${d.precio} · Zona #{d.zona_id}
              </p>
              <p className="tenue">
                Orden #{d.orden_id} · Evento #{d.evento_id} · Cliente #{d.user_id}
                {d.evento_fecha_inicio && ` · ${formatearFecha(d.evento_fecha_inicio)}`}
              </p>
              {d.evento_cancelado && <p><strong>Evento cancelado</strong></p>}
              {d.motivo && <p>Motivo del cliente: {d.motivo}</p>}
              {d.nota_resolucion && <p className="tenue">Nota de resolución: {d.nota_resolucion}</p>}
              {d.estado === "pendiente" && (
                <div>
                  <label>
                    Nota de resolución (opcional)
                    <input
                      type="text"
                      maxLength={500}
                      value={notas[d.id] ?? ""}
                      onChange={(e) => setNotas((prev) => ({ ...prev, [d.id]: e.target.value }))}
                      placeholder="Observaciones para el cliente"
                    />
                  </label>
                  <button
                    type="button"
                    disabled={procesando.has(d.id)}
                    onClick={() => resolver(d.id, "aprobar")}
                  >
                    Aprobar
                  </button>
                  <button
                    type="button"
                    disabled={procesando.has(d.id)}
                    onClick={() => resolver(d.id, "rechazar")}
                  >
                    Rechazar
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
