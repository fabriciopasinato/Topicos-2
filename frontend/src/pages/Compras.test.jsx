import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { API, server } from "../test/server.js";
import { iniciarSesion, renderEn } from "../test/utilidades.jsx";

describe("historial de compras", () => {
  test("lista las órdenes pagadas con sus tickets", async () => {
    iniciarSesion();
    server.use(
      http.get(`${API}/api/ventas/compras`, () =>
        HttpResponse.json([
          {
            id: 9, reserva_id: 55, total: 3000, created_at: "2026-11-07T20:00:00Z",
            tickets: [
              { ticket_id: 101, evento_id: 1, zona_id: 10, fila: "A", numero: 1, precio: 1500 },
              { ticket_id: 102, evento_id: 1, zona_id: 10, fila: "A", numero: 2, precio: 1500 },
            ],
          },
        ]),
      ),
    );
    renderEn("/compras");
    expect(await screen.findByRole("heading", { name: "Orden #9" })).toBeInTheDocument();
    expect(screen.getByText("Asiento A-2 · $1500")).toBeInTheDocument();
    expect(screen.getByText("Total: $3000")).toBeInTheDocument();
  });

  test("sin compras", async () => {
    iniciarSesion();
    server.use(http.get(`${API}/api/ventas/compras`, () => HttpResponse.json([])));
    renderEn("/compras");
    expect(await screen.findByText("Todavía no compraste entradas.")).toBeInTheDocument();
  });

  test("sin sesión redirige al login", async () => {
    renderEn("/compras");
    expect(await screen.findByRole("heading", { name: "Ingresar" })).toBeInTheDocument();
  });
});
