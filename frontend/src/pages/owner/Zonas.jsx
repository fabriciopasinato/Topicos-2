import { useState } from "react";
import { api } from "../../api/client.js";
import Mensaje from "../../components/Mensaje.jsx";
import { mensaje } from "./comun.js";

const ZONA_VACIA = { nombre: "", tipo: "general", precio: "", capacidad: "", filas: "", asientos_por_fila: "" };

function NuevaZona({ eventoId, sectorId, alCambiar }) {
  const [zona, setZona] = useState(ZONA_VACIA);
  const [error, setError] = useState("");
  const cambiar = (campo) => (e) => setZona((z) => ({ ...z, [campo]: e.target.value }));

  async function agregar() {
    const cuerpo = { nombre: zona.nombre, tipo: zona.tipo, precio: zona.precio };
    if (zona.tipo === "numerada") {
      cuerpo.filas = zona.filas.split(",").map((f) => f.trim()).filter(Boolean);
      cuerpo.asientos_por_fila = Number(zona.asientos_por_fila);
    } else {
      cuerpo.capacidad = Number(zona.capacidad);
    }
    try {
      await api(`/api/eventos/${eventoId}/sectores/${sectorId}/zonas`, { method: "POST", body: cuerpo });
      setZona(ZONA_VACIA);
      setError("");
      alCambiar();
    } catch (e) {
      setError(mensaje(e, "Revisá la zona: capacidad o asientos mayores a 0 y precio no negativo."));
    }
  }

  return (
    <fieldset>
      <legend>Agregar zona</legend>
      <label>
        Nombre de la zona
        <input value={zona.nombre} onChange={cambiar("nombre")} />
      </label>
      <label>
        Tipo de zona
        <select value={zona.tipo} onChange={cambiar("tipo")}>
          <option value="general">General (sin numerar)</option>
          <option value="numerada">Numerada</option>
        </select>
      </label>
      <label>
        Precio
        <input type="number" min="0" step="0.01" value={zona.precio} onChange={cambiar("precio")} />
      </label>
      {zona.tipo === "numerada" ? (
        <>
          <label>
            Filas (separadas por coma)
            <input value={zona.filas} onChange={cambiar("filas")} />
          </label>
          <label>
            Asientos por fila
            <input type="number" min="1" value={zona.asientos_por_fila} onChange={cambiar("asientos_por_fila")} />
          </label>
        </>
      ) : (
        <label>
          Capacidad
          <input type="number" min="1" value={zona.capacidad} onChange={cambiar("capacidad")} />
        </label>
      )}
      <Mensaje>{error}</Mensaje>
      <button type="button" disabled={!zona.nombre.trim() || zona.precio === ""} onClick={agregar}>
        Agregar zona
      </button>
    </fieldset>
  );
}

/** Sectores y zonas. `editable` solo en borrador: publicado, el inventario ya esta en ventas. */
export default function Zonas({ evento, editable, alCambiar }) {
  const [sector, setSector] = useState("");
  const [error, setError] = useState("");

  async function agregarSector() {
    try {
      await api(`/api/eventos/${evento.id}/sectores`, { method: "POST", body: { nombre: sector } });
      setSector("");
      alCambiar();
    } catch (e) {
      setError(mensaje(e, "No se pudo agregar el sector."));
    }
  }

  async function borrarZona(zonaId) {
    try {
      await api(`/api/eventos/${evento.id}/zonas/${zonaId}`, { method: "DELETE" });
      alCambiar();
    } catch (e) {
      setError(mensaje(e, "No se pudo borrar la zona."));
    }
  }

  return (
    <section>
      <h2>Sectores y zonas</h2>
      {evento.sectores.length === 0 && <p className="tenue">Todavía no hay sectores.</p>}
      {evento.sectores.map((s) => (
        <article key={s.id} className="tarjeta">
          <h3>{s.nombre}</h3>
          <ul>
            {s.zonas.map((z) => (
              <li key={z.id}>
                {z.nombre} · {z.tipo === "numerada" ? "numerada" : "general"} · {z.capacidad} lugares · ${z.precio}{" "}
                {editable && (
                  <button type="button" className="enlace" onClick={() => borrarZona(z.id)}>
                    Borrar zona {z.nombre}
                  </button>
                )}
              </li>
            ))}
          </ul>
          {editable && <NuevaZona eventoId={evento.id} sectorId={s.id} alCambiar={alCambiar} />}
        </article>
      ))}
      {editable && (
        <div className="acciones">
          <label>
            Nuevo sector
            <input value={sector} onChange={(e) => setSector(e.target.value)} />
          </label>
          <button type="button" disabled={!sector.trim()} onClick={agregarSector}>
            Agregar sector
          </button>
        </div>
      )}
      <Mensaje>{error}</Mensaje>
    </section>
  );
}
