import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mensajeDeError } from "../../api/client.js";
import Mensaje from "../../components/Mensaje.jsx";

const TAMANIO = 20;
const ESTADOS = { activa: "Activa", pendiente_verificacion: "Sin verificar", bloqueada: "Bloqueada" };

export default function AdminUsuarios() {
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState("");
  const [pagina, setPagina] = useState(1);
  const [resultado, setResultado] = useState(null);
  const [error, setError] = useState("");

  const buscar = useCallback(async (busqueda, filtroEstado, nroPagina) => {
    const params = new URLSearchParams({ pagina: nroPagina, tamanio: TAMANIO });
    if (busqueda) params.set("q", busqueda);
    if (filtroEstado) params.set("estado", filtroEstado);
    try {
      setResultado(await api(`/api/auth/admin/usuarios?${params}`));
      setError("");
    } catch (e) {
      setError(mensajeDeError(e));
    }
  }, []);

  useEffect(() => {
    buscar("", "", 1);
  }, [buscar]);

  function enviar(e) {
    e.preventDefault();
    setPagina(1);
    buscar(q, estado, 1);
  }

  function irA(nro) {
    setPagina(nro);
    buscar(q, estado, nro);
  }

  const paginas = resultado ? Math.max(1, Math.ceil(resultado.total / TAMANIO)) : 1;

  return (
    <section>
      <h1>Cuentas</h1>
      <p><Link to="/admin/event-owners">Dar de alta un organizador</Link></p>
      <form onSubmit={enviar} className="filtros">
        <label>
          Buscar
          <input type="search" placeholder="Email, apellido o DNI" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <label>
          Estado
          <select value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="">Todos</option>
            {Object.entries(ESTADOS).map(([valor, nombre]) => (
              <option key={valor} value={valor}>{nombre}</option>
            ))}
          </select>
        </label>
        <button type="submit">Buscar</button>
      </form>

      <Mensaje>{error}</Mensaje>
      {resultado && (
        <>
          <p className="tenue">{resultado.total} cuenta(s)</p>
          <table className="tabla">
            <thead>
              <tr><th>Email</th><th>Apellido y nombre</th><th>DNI</th><th>Rol</th><th>Estado</th></tr>
            </thead>
            <tbody>
              {resultado.items.map((u) => (
                <tr key={u.id}>
                  <td><Link to={`/admin/usuarios/${u.id}`}>{u.email}</Link></td>
                  <td>{[u.apellido, u.nombre].filter(Boolean).join(", ") || "-"}</td>
                  <td>{u.dni ?? "-"}</td>
                  <td>{u.rol}</td>
                  <td>{ESTADOS[u.estado] ?? u.estado}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="acciones">
            <button type="button" className="secundario" disabled={pagina <= 1} onClick={() => irA(pagina - 1)}>
              Anterior
            </button>
            <span>Página {pagina} de {paginas}</span>
            <button type="button" className="secundario" disabled={pagina >= paginas} onClick={() => irA(pagina + 1)}>
              Siguiente
            </button>
          </div>
        </>
      )}
    </section>
  );
}
