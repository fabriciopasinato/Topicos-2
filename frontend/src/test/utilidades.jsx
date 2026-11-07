import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AppConRouter } from "../App.jsx";
import { guardarTokens } from "../api/client.js";

/** JWT de mentira (el frontend solo lee sub y rol; la firma la valida el gateway). */
export function tokenFalso(sub = 20, rol = "cliente") {
  const b64 = (o) => btoa(JSON.stringify(o)).replace(/=+$/, "");
  return `${b64({ alg: "HS256" })}.${b64({ sub: String(sub), rol })}.firma`;
}

export function iniciarSesion(rol = "cliente") {
  guardarTokens({ access_token: tokenFalso(20, rol), refresh_token: "R1" });
}

/** Renderiza la app completa en la ruta indicada. */
export function renderEn(ruta) {
  const user = userEvent.setup();
  const utils = render(<AppConRouter Router={MemoryRouter} routerProps={{ initialEntries: [ruta] }} />);
  return { user, ...utils };
}

export const EVENTO = {
  id: 1,
  nombre: "Recital de prueba",
  fecha: "2026-12-20T21:00:00Z",
  estado: "publicado",
  owner_id: 10,
  recinto: { id: 1, nombre: "Estadio Central", direccion: "" },
  sectores: [
    {
      id: 1,
      nombre: "Platea",
      zonas: [
        { id: 10, nombre: "Platea A", tipo: "numerada", capacidad: 3, precio: 1500, asientos: [] },
        { id: 20, nombre: "Campo", tipo: "general", capacidad: 10, precio: 800, asientos: [] },
      ],
    },
  ],
};

export const DISPONIBILIDAD = {
  evento_id: 1,
  zonas: [
    {
      zona_id: 10, tipo: "numerada", precio: 1500, disponibles: 2, total: 3,
      asientos: [
        { ticket_id: 101, fila: "A", numero: 1, disponible: true },
        { ticket_id: 102, fila: "A", numero: 2, disponible: true },
        { ticket_id: 103, fila: "A", numero: 3, disponible: false },
      ],
    },
    { zona_id: 20, tipo: "general", precio: 800, disponibles: 10, total: 10, asientos: [] },
  ],
};
