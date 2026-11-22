import { useCallback, useEffect, useState } from "react";
import { api, mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";
import { formatearFecha } from "./Cartelera.jsx";

const ETIQUETA_DEVOLUCION = {
  pendiente: "Devolución pendiente",
  aprobada: "Devolución aprobada",
  rechazada: "Devolución rechazada",
};

const ETIQUETA_EVENTO = {
  cancelado: "Evento cancelado",
  finalizado: "Evento finalizado",
};

function puedeSolicitarDevolucion(ticket) {
  if (!ticket.orden_item_id) return false;
  if (ticket.evento_estado === "finalizado") return false;
  return !ticket.devolucion || ticket.devolucion.estado === "rechazada";
}

export default function Compras() {
  const [compras, setCompras] = useState(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [itemActivo, setItemActivo] = useState(null);
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);

    const cargar = useCallback(async () => {
      try {
        const datos = await api("/api/ventas/compras");
        setCompras(datos);
      } catch (e) {
        setError(mensajeDeError(e));
      }
    }, []);

    useEffect(() => {
      cargar();
    }, [cargar]);

    async function enviarDevolucion(e) {
      e.preventDefault();
      if (!itemActivo) return;
      setEnviando(true);
      setError("");
      setAviso("");
      try {
        await api("/api/ventas/devoluciones", {
          method: "POST",
          body: { orden_item_id: itemActivo, motivo: motivo.trim() || null },
        });
        setItemActivo(null);
        setMotivo("");
        setAviso("Solicitud de devolución enviada.");
        await cargar();
      } catch (err) {
        setError(mensajeDeError(err));
      } finally {
        setEnviando(false);
      }
    }

    if (error && !compras) return <Mensaje>{error}</Mensaje>;
    if (!compras) return <p>Cargando compras…</p>;

    return (
      <section>
        <h1>Mis compras</h1>
        <Mensaje tipo="info">{aviso}</Mensaje>
        <Mensaje>{error}</Mensaje>
        {compras.length === 0 ? (
          <p>Todavía no compraste entradas.</p>
        ) : (
          <ul className="lista">
            {compras.map((c) => (
              <li key={c.id} className="tarjeta">
                <h2>Orden #{c.id}</h2>
                <ul>
                  {c.tickets.map((t) => {
                    const etiquetaEvento = ETIQUETA_EVENTO[t.evento_estado];
                    const etiquetaDev = t.devolucion ? ETIQUETA_DEVOLUCION[t.devolucion.estado] : null;
                    const abierto = itemActivo === t.orden_item_id;
                    return (
                      <li key={t.orden_item_id ?? t.ticket_id}>
                        <span>{t.fila ? `Asiento ${t.fila}-${t.numero}` : "Entrada general"} · ${t.precio}</span>
                        {t.evento_fecha_inicio && (
                          <span className="tenue"> · {formatearFecha(t.evento_fecha_inicio)}</span>
                        )}
                        {etiquetaEvento && <span> · {etiquetaEvento}</span>}
                        {etiquetaDev && (
                          <div>
                            <span>{etiquetaDev}</span>
                            {t.devolucion?.nota_resolucion && (
                              <span className="tenue"> ({t.devolucion.nota_resolucion})</span>
                            )}
                          </div>
                        )}
                        {puedeSolicitarDevolucion(t) && !abierto && (
                          <div>
                            <button
                              type="button"
                              onClick={() => {
                                setItemActivo(t.orden_item_id);
                                setMotivo("");
                                setError("");
                                setAviso("");
                              }}
                            >
                              Solicitar devolución
                            </button>
                          </div>
                        )}
                        {abierto && (
                          <form onSubmit={enviarDevolucion}>
                            <label>
                              Motivo (opcional)
                              <input
                                type="text"
                                maxLength={500}
                                value={motivo}
                                onChange={(e) => setMotivo(e.target.value)}
                                placeholder="Contanos el motivo"
                              />
                            </label>
                            <button type="submit" disabled={enviando}>
                              Confirmar devolución
                            </button>
                            <button
                              type="button"
                              disabled={enviando}
                              onClick={() => {
                                setItemActivo(null);
                                setMotivo("");
                              }}
                            >
                              Cancelar
                            </button>
                          </form>
                        )}
                      </li>
                    );
                  })}
                </ul>
                <p>Total: ${c.total}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  }
