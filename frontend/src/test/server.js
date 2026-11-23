import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const API = "http://localhost:8000";

// Unico handler por defecto: el catalogo de tipos, que usan casi todas las pantallas.
// El resto lo registra cada test con server.use(...).
export const server = setupServer(
  http.get(`${API}/api/eventos/tipos`, () =>
    HttpResponse.json([
      { codigo: "recital", nombre: "Recital" },
      { codigo: "teatro", nombre: "Teatro" },
    ]),
  ),
);
