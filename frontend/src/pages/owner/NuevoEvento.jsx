import { useNavigate } from "react-router-dom";
import FormularioEvento from "./FormularioEvento.jsx";

export default function NuevoEvento() {
  const navigate = useNavigate();
  return (
    <section className="angosta">
      <h1>Nuevo evento</h1>
      <FormularioEvento alGuardar={(evento) => navigate(`/owner/eventos/${evento.id}`)} />
    </section>
  );
}
