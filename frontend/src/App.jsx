import { useEffect } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { configurarAlFallarAuth } from "./api/client.js";
import { SesionProvider, useSesion } from "./auth/sesion.jsx";
import Cartelera from "./pages/Cartelera.jsx";
import Compras from "./pages/Compras.jsx";
import Evento from "./pages/Evento.jsx";
import Login from "./pages/Login.jsx";
import Registro from "./pages/Registro.jsx";
import Reserva from "./pages/Reserva.jsx";

function SoloConSesion({ children }) {
  const { usuario } = useSesion();
  return usuario ? children : <Navigate to="/login" replace />;
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
