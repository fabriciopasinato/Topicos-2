import { useEffect } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { configurarAlFallarAuth } from "./api/client.js";
import { SesionProvider, useSesion } from "./auth/sesion.jsx";
import Cartelera from "./pages/Cartelera.jsx";
import Compras from "./pages/Compras.jsx";
import AdminDevoluciones from "./pages/AdminDevoluciones.jsx";
import Evento from "./pages/Evento.jsx";
import Login from "./pages/Login.jsx";
import GestionEvento from "./pages/owner/GestionEvento.jsx";
import MisEventos from "./pages/owner/MisEventos.jsx";
import NuevoEvento from "./pages/owner/NuevoEvento.jsx";
import Registro from "./pages/Registro.jsx";
import Reserva from "./pages/Reserva.jsx";

export const ROLES_GESTORES = ["event_owner", "administrador"];

function SoloConSesion({ children }) {
  const { usuario } = useSesion();
  return usuario ? children : <Navigate to="/login" replace />;
}

/** Solo para los roles indicados; el resto vuelve a la portada. */
function SoloRol({ roles, children }) {
  const { usuario } = useSesion();
  if (!usuario) return <Navigate to="/login" replace />;
  return roles.includes(usuario.rol) ? children : <Navigate to="/" replace />;
}

function Encabezado() {
  const { usuario, logout } = useSesion();
  return (
    <header className="encabezado">
      <Link to="/" className="marca">
        Ticketera
      </Link>
      <nav>
        {usuario ? (
          <>
            {ROLES_GESTORES.includes(usuario.rol) && <Link to="/owner">Mis eventos</Link>}
            {usuario.rol === "administrador" && <Link to="/admin/devoluciones">Devoluciones</Link>}
            <Link to="/compras">Mis compras</Link>
            <button type="button" className="enlace" onClick={logout}>
              Salir
            </button>
          </>
        ) : (
          <>
            <Link to="/login">Ingresar</Link>
            <Link to="/registro">Registrarme</Link>
          </>
        )}
      </nav>
    </header>
  );
}

function Rutas() {
  const navigate = useNavigate();
  useEffect(() => {
    configurarAlFallarAuth(() =>
      navigate("/login", { state: { aviso: "Tu sesión expiró. Ingresá de nuevo." } }),
    );
  }, [navigate]);

  return (
    <>
      <Encabezado />
      <main>
        <Routes>
          <Route path="/" element={<Cartelera />} />
          <Route path="/login" element={<Login />} />
          <Route path="/registro" element={<Registro />} />
          <Route path="/eventos/:id" element={<Evento />} />
          <Route path="/reservas/:id" element={<SoloConSesion><Reserva /></SoloConSesion>} />
          <Route path="/compras" element={<SoloConSesion><Compras /></SoloConSesion>} />
          <Route path="/owner" element={<SoloRol roles={ROLES_GESTORES}><MisEventos /></SoloRol>} />
          <Route path="/owner/eventos/nuevo" element={<SoloRol roles={ROLES_GESTORES}><NuevoEvento /></SoloRol>} />
          <Route path="/owner/eventos/:id" element={<SoloRol roles={ROLES_GESTORES}><GestionEvento /></SoloRol>} />
          <Route path="/admin/devoluciones" element={<SoloRol roles={["administrador"]}><AdminDevoluciones /></SoloRol>} />
          <Route path="*" element={<p>Página no encontrada.</p>} />
        </Routes>
      </main>
    </>
  );
}

/** App con un router configurable (los tests usan MemoryRouter). */
export function AppConRouter({ Router = BrowserRouter, routerProps = {} }) {
  return (
    <SesionProvider>
      <Router {...routerProps}>
        <Rutas />
      </Router>
    </SesionProvider>
  );
}

export default function App() {
  return <AppConRouter />;
}
