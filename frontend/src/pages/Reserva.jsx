import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, mensajeDeError } from "../api/client.js";
import Mensaje from "../components/Mensaje.jsx";

function segundosRestantes(hasta) {
  return Math.max(0, Math.ceil((new Date(hasta).getTime() - Date.now()) / 1000));
}

function mmss(segundos) {
  const m = Math.floor(segundos / 60);
  const s = String(segundos % 60).padStart(2, "0");
  return `${m}:${s}`;
}

export default function Reserva() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [reserva, setReserva] = useState(null);
  const [restante, setRestante] = useState(null);
  const [orden, setOrden] = useState(null);
  const [vencida, setVencida] = useState(false);
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  const cargar = useCallback(() => {
    api(`/api/ventas/reservas/${id}`)
      .then((r) => {
        setReserva(r);
        setVencida(r.estado === "vencida" || r.estado === "cancelada");
        setRestante(segundosRestantes(r.hasta));
      })
      .catch((e) => setError(mensajeDeError(e, { 404: "La reserva no existe." })));
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Cuenta regresiva hasta el vencimiento.
  useEffect(() => {
    if (!reserva || reserva.estado !== "activa" || orden) return undefined;
    const intervalo = setInterval(() => {
      const s = segundosRestantes(reserva.hasta);
      setRestante(s);
      if (s === 0) {
        setVencida(true);
        clearInterval(intervalo);
      }
    }, 1000);
    return () => clearInterval(intervalo);
  }, [reserva, orden]);

  async function pagar() {
    setEnviando(true);
    setError("");
    try {
      setOrden(await api(`/api/ventas/reservas/${id}/pago`, { method: "POST" }));
    } catch (e) {
      if (e.status === 409) setVencida(true);
      else setError(mensajeDeError(e));
    } finally {
      setEnviando(false);
    }
  }

  async function cancelar() {
    setEnviando(true);
    try {
      await api(`/api/ventas/reservas/${id}`, { method: "DELETE" });
      navigate(`/eventos/${reserva.evento_id}`);
    } catch (e) {
      setError(mensajeDeError(e));
      setEnviando(false);
    }
  }

  if (!reserva) return error ? <Mensaje>{error}</Mensaje> : <p>Cargando reserva…</p>;

  if (orden || reserva.estado === "pagada") {
    return (
      <section className="tarjeta angosta">
        <h1>¡Compra confirmada!</h1>
        <p>Total pagado: ${orden?.total ?? reserva.total}</p>
        <Link to="/compras">Ver mis compras</Link>
      </section>
    );
  }

  if (vencida) {
    return (
      <section className="tarjeta angosta">
        <h1>La reserva venció</h1>
        <p>Los tickets volvieron a estar disponibles para otros compradores.</p>
        <Link to={`/eventos/${reserva.evento_id}`}>Volver a elegir</Link>
      </section>
    );
  }

  return (
    <section className="tarjeta angosta">
      <h1>Tu reserva</h1>
      <p className="cuenta-regresiva" aria-live="polite">
        Tenés <strong>{mmss(restante)}</strong> para pagar
      </p>
      <ul>
        {reserva.tickets.map((t) => (
          <li key={t.id}>
            {t.tipo_zona === "numerada" ? `Asiento ${t.fila}-${t.numero}` : "Entrada general"} · ${t.precio}
          </li>
        ))}
      </ul>
      <p>Total: ${reserva.total}</p>
      <Mensaje>{error}</Mensaje>
      <div className="acciones">
        <button type="button" onClick={pagar} disabled={enviando}>
          Pagar
        </button>
        <button type="button" className="secundario" onClick={cancelar} disabled={enviando}>
          Cancelar reserva
        </button>
      </div>
    </section>
  );
}
