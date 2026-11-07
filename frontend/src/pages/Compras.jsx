import { useEffect, useState } from "react";
import { api, mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";

export default function Compras() {
  const [compras, setCompras] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/ventas/compras").then(setCompras).catch((e) => setError(mensajeDeError(e)));
  }, []);

  if (error) return <Mensaje>{error}</Mensaje>;
  if (!compras) return <p>Cargando compras…</p>;

  return (
    <section>
      <h1>Mis compras</h1>
      {compras.length === 0 ? (
        <p>Todavía no compraste entradas.</p>
      ) : (
        <ul className="lista">
          {compras.map((c) => (
            <li key={c.id} className="tarjeta">
              <h2>Orden #{c.id}</h2>
              <ul>
                {c.tickets.map((t) => (
                  <li key={t.ticket_id}>
                    {t.fila ? `Asiento ${t.fila}-${t.numero}` : "Entrada general"} · ${t.precio}
                  </li>
                ))}
              </ul>
              <p>Total: ${c.total}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
