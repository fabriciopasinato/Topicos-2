import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, mensajeDeError } from "../../api/client.js";
import Mensaje from "../../components/Mensaje.jsx";
import { formatearFecha } from "../Cartelera.jsx";
import FormularioEvento from "./FormularioEvento.jsx";
import Zonas from "./Zonas.jsx";
import { aIso, mensaje, NOMBRE_ESTADO, puede, textoPendiente } from "./comun.js";

function Confirmable({ etiqueta, pregunta, confirmar }) {
  const [preguntando, setPreguntando] = useState(false);
  if (!preguntando) {
    return (
      <button type="button" className="secundario" onClick={() => setPreguntando(true)}>
        {etiqueta}
      </button>
    );
  }
  return (
    <span className="acciones">
      <span>{pregunta}</span>
      <button type="button" onClick={() => { setPreguntando(false); confirmar(); }}>
        Sí, {etiqueta.toLowerCase()}
      </button>
      <button type="button" className="secundario" onClick={() => setPreguntando(false)}>
        No
      </button>
    </span>
  );
}

export default function GestionEvento() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [evento, setEvento] = useState(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [nuevaFecha, setNuevaFecha] = useState("");

  const cargar = useCallback(async () => {
    try {
      setEvento(await api(`/api/eventos/${id}`));
    } catch (e) {
      setError(mensajeDeError(e, { 404: "El evento no existe." }));
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function ejecutar(accion, aplicado, enProceso) {
    setError("");
    setAviso("");
    try {
      const resultado = await accion();
      setEvento(resultado);
      setAviso(resultado.operaciones_pendientes?.length ? enProceso : aplicado);
    } catch (e) {
      setError(mensaje(e, "No se pudo completar la operación."));
    }
  }

  const publicar = () =>
    ejecutar(() => api(`/api/eventos/${id}/publicar`, { method: "POST" }), "Evento publicado.", "Evento publicado.");

  const reprogramar = () =>
    ejecutar(
      () => api(`/api/eventos/${id}/reprogramar`, { method: "POST", body: { fecha: aIso(nuevaFecha) } }),
      "Evento reprogramado.",
      "La reprogramación está en proceso: se completará cuando ventas esté disponible.",
    );

  const cancelar = () =>
    ejecutar(
      () => api(`/api/eventos/${id}/cancelar`, { method: "POST" }),
      "Evento cancelado.",
      "La cancelación está en proceso: se completará cuando ventas esté disponible.",
    );

  async function borrar() {
    try {
      await api(`/api/eventos/${id}`, { method: "DELETE" });
      navigate("/owner");
    } catch (e) {
      setError(mensaje(e, "No se pudo borrar el evento."));
    }
  }

  if (!evento) return error ? <Mensaje>{error}</Mensaje> : <p>Cargando evento…</p>;

  return (
    <section>
      <h1>
        {evento.nombre} <span className="estado">{NOMBRE_ESTADO[evento.estado] ?? evento.estado}</span>
      </h1>
      <p>
        {formatearFecha(evento.fecha)} · {evento.recinto.nombre}
      </p>
      {evento.operaciones_pendientes.map((op, i) => (
        <Mensaje key={i} tipo="info">
          {textoPendiente(op)}
        </Mensaje>
      ))}
      <Mensaje>{error}</Mensaje>
      <Mensaje tipo="info">{aviso}</Mensaje>

      <div className="acciones">
        {puede(evento, "publicar") && (
          <button type="button" onClick={publicar}>
            Publicar
          </button>
        )}
        {puede(evento, "cancelar") && (
          <Confirmable
            etiqueta="Cancelar evento"
            pregunta="Se cancela el evento y ventas deja de vender sus entradas. ¿Seguro?"
            confirmar={cancelar}
          />
        )}
        {puede(evento, "borrar") && (
          <Confirmable etiqueta="Borrar borrador" pregunta="Se borra el evento con sus zonas. ¿Seguro?" confirmar={borrar} />
        )}
      </div>

      {puede(evento, "reprogramar") && (
        <div className="acciones">
          <label>
            Nueva fecha y hora
            <input type="datetime-local" value={nuevaFecha} onChange={(e) => setNuevaFecha(e.target.value)} />
          </label>
          <button type="button" disabled={!nuevaFecha} onClick={reprogramar}>
            Reprogramar
          </button>
        </div>
      )}

      {puede(evento, "editar") && (
        <section className="angosta">
          <h2>Datos del evento</h2>
          <FormularioEvento key={evento.id} evento={evento} alGuardar={setEvento} />
        </section>
      )}

      <Zonas evento={evento} editable={puede(evento, "zonas")} alCambiar={cargar} />
    </section>
  );
}
