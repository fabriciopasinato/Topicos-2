import { useEffect, useState } from "react";
import { api, mensajeDeError } from "../../api/client.js";
import Mensaje from "../../components/Mensaje.jsx";
import { aIso, mensaje, puede } from "./comun.js";

function separar(texto) {
  return texto.split(",").map((s) => s.trim()).filter(Boolean);
}

function NuevoRecinto({ alCrear }) {
  const [abierto, setAbierto] = useState(false);
  const [nombre, setNombre] = useState("");
  const [direccion, setDireccion] = useState("");
  const [error, setError] = useState("");

  async function crear() {
    try {
      alCrear(await api("/api/eventos/recintos", { method: "POST", body: { nombre, direccion } }));
      setAbierto(false);
      setNombre("");
      setDireccion("");
    } catch (e) {
      setError(mensaje(e, "Revisá el nombre del recinto."));
    }
  }

  if (!abierto) {
    return (
      <button type="button" className="enlace" onClick={() => setAbierto(true)}>
        Agregar un recinto
      </button>
    );
  }
  return (
    <div className="tarjeta">
      <label>
        Nombre del recinto
        <input value={nombre} onChange={(e) => setNombre(e.target.value)} />
      </label>
      <label>
        Dirección
        <input value={direccion} onChange={(e) => setDireccion(e.target.value)} />
      </label>
      <Mensaje>{error}</Mensaje>
      <button type="button" disabled={!nombre.trim()} onClick={crear}>
        Guardar recinto
      </button>
    </div>
  );
}

/** Alta (sin `evento`) o edición de un evento. La fecha solo se elige en el alta. */
export default function FormularioEvento({ evento, alGuardar }) {
  const edicion = Boolean(evento);
  const [tipos, setTipos] = useState([]);
  const [recintos, setRecintos] = useState([]);
  const [datos, setDatos] = useState({
    nombre: evento?.nombre ?? "",
    fecha: "",
    recinto_id: evento?.recinto.id ?? "",
    tipo: evento?.tipo ?? "",
    organizador: evento?.organizador?.nombre ?? "",
    participantes: (evento?.participantes ?? []).map((p) => p.nombre).join(", "),
    descripcion: evento?.descripcion ?? "",
  });
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [enviando, setEnviando] = useState(false);
  const recintoEditable = !edicion || puede(evento, "cambiar_recinto");

  useEffect(() => {
    Promise.all([api("/api/eventos/tipos"), api("/api/eventos/recintos")])
      .then(([t, r]) => {
        setTipos(t);
        setRecintos(r);
      })
      .catch((e) => setError(mensajeDeError(e)));
  }, []);

  const cambiar = (campo) => (e) => setDatos((d) => ({ ...d, [campo]: e.target.value }));

  async function guardar(e) {
    e.preventDefault();
    setEnviando(true);
    setError("");
    setAviso("");
    const cuerpo = {
      nombre: datos.nombre,
      tipo: datos.tipo,
      organizador: datos.organizador,
      participantes: separar(datos.participantes),
      descripcion: datos.descripcion,
    };
    if (recintoEditable) cuerpo.recinto_id = Number(datos.recinto_id);
    try {
      const guardado = edicion
        ? await api(`/api/eventos/${evento.id}`, { method: "PATCH", body: cuerpo })
        : await api("/api/eventos", { method: "POST", body: { ...cuerpo, fecha: aIso(datos.fecha) } });
      if (edicion) setAviso("Cambios guardados.");
      alGuardar(guardado);
    } catch (err) {
      setError(mensaje(err, "Revisá los datos del evento."));
    } finally {
      setEnviando(false);
    }
  }

  const completo =
    datos.nombre.trim() && datos.tipo && datos.organizador.trim() && datos.recinto_id && (edicion || datos.fecha);

  return (
    <form onSubmit={guardar}>
      <label>
        Nombre
        <input value={datos.nombre} onChange={cambiar("nombre")} />
      </label>
      {!edicion && (
        <label>
          Fecha y hora de inicio
          <input type="datetime-local" value={datos.fecha} onChange={cambiar("fecha")} />
        </label>
      )}
      <label>
        Tipo
        <select value={datos.tipo} onChange={cambiar("tipo")}>
          <option value="">Elegí un tipo</option>
          {tipos.map((t) => (
            <option key={t.codigo} value={t.codigo}>
              {t.nombre}
            </option>
          ))}
        </select>
      </label>
      <label>
        Recinto
        <select value={datos.recinto_id} onChange={cambiar("recinto_id")} disabled={!recintoEditable}>
          <option value="">Elegí un recinto</option>
          {recintos.map((r) => (
            <option key={r.id} value={r.id}>
              {r.nombre}
            </option>
          ))}
        </select>
      </label>
      {recintoEditable && (
        <NuevoRecinto
          alCrear={(r) => {
            setRecintos((rs) => [...rs, r]);
            setDatos((d) => ({ ...d, recinto_id: r.id }));
          }}
        />
      )}
      <label>
        Organizador
        <input value={datos.organizador} onChange={cambiar("organizador")} />
      </label>
      <label>
        Participantes (separados por coma)
        <input value={datos.participantes} onChange={cambiar("participantes")} />
      </label>
      <label>
        Descripción
        <textarea value={datos.descripcion} onChange={cambiar("descripcion")} />
      </label>
      <Mensaje>{error}</Mensaje>
      <Mensaje tipo="info">{aviso}</Mensaje>
      <button type="submit" disabled={!completo || enviando}>
        {edicion ? "Guardar cambios" : "Crear evento"}
      </button>
    </form>
  );
}
