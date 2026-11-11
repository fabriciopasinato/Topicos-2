import { useEffect } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { configurarAlFallarAuth } from "./api/client.js";
import { AVISO_SESION_CERRADA, SesionProvider, useSesion } from "./auth/sesion.jsx";
import AdminEventOwners from "./pages/admin/AdminEventOwners.jsx";
import AdminUsuario from "./pages/admin/AdminUsuario.jsx";
import AdminUsuarios from "./pages/admin/AdminUsuarios.jsx";
import CambiarContrasenia from "./pages/CambiarContrasenia.jsx";
import Cartelera from "./pages/Cartelera.jsx";
import Compras from "./pages/Compras.jsx";
import Evento from "./pages/Evento.jsx";
import Login from "./pages/Login.jsx";
import Olvide from "./pages/Olvide.jsx";
import Perfil from "./pages/Perfil.jsx";
import Registro from "./pages/Registro.jsx";
import Reserva from "./pages/Reserva.jsx";
import Restablecer from "./pages/Restablecer.jsx";
import Verificar from "./pages/Verificar.jsx";

function AlLogin() {
  const { avisoCierre } = useSesion();
  return <Navigate to="/login" replace state={avisoCierre ? { aviso: avisoCierre } : undefined} />;
}

function SoloConSesion({ children }) {
  const { usuario } = useSesion();
  return usuario ? children : <AlLogin />;
}

/** Solo para los roles indicados; el resto vuelve a la portada. */
function SoloRol({ roles, children }) {
  const { usuario } = useSesion();
  if (!usuario) return <AlLogin />;
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
            {usuario.rol === "administrador" && <Link to="/admin/usuarios">Administración</Link>}
            <Link to="/compras">Mis compras</Link>
            <Link to="/perfil">Mi perfil</Link>
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
      navigate("/login", { state: { aviso: AVISO_SESION_CERRADA } }),
    );
  }, [navigate]);

  const admin = (pagina) => <SoloRol roles={["administrador"]}>{pagina}</SoloRol>;

  return (
    <>
      <Encabezado />
      <main>
        <Routes>
          <Route path="/" element={<Cartelera />} />
          <Route path="/login" element={<Login />} />
          <Route path="/registro" element={<Registro />} />
          <Route path="/verificar" element={<Verificar />} />
          <Route path="/olvide" element={<Olvide />} />
          <Route path="/restablecer" element={<Restablecer />} />
          <Route path="/eventos/:id" element={<Evento />} />
          <Route path="/reservas/:id" element={<SoloConSesion><Reserva /></SoloConSesion>} />
          <Route path="/compras" element={<SoloConSesion><Compras /></SoloConSesion>} />
          <Route path="/perfil" element={<SoloConSesion><Perfil /></SoloConSesion>} />
          <Route path="/perfil/contrasenia" element={<SoloConSesion><CambiarContrasenia /></SoloConSesion>} />
          <Route path="/admin/usuarios" element={admin(<AdminUsuarios />)} />
          <Route path="/admin/usuarios/:id" element={admin(<AdminUsuario />)} />
          <Route path="/admin/event-owners" element={admin(<AdminEventOwners />)} />
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
