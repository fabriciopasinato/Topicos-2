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
              {
                orden_item_id: 501, ticket_id: 101, evento_id: 1, zona_id: 10, tipo_zona: "numerada",
                fila: "A", numero: 1, precio: 1500, evento_fecha_inicio: "2026-12-20T21:00:00Z",
                evento_cancelado: false, evento_estado: "activo", devolucion: null,
              },
              {
                orden_item_id: 502, ticket_id: 102, evento_id: 1, zona_id: 10, tipo_zona: "numerada",
                fila: "A", numero: 2, precio: 1500, evento_fecha_inicio: "2026-12-20T21:00:00Z",
                evento_cancelado: false, evento_estado: "activo", devolucion: null,
              },
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

  test("permite solicitar devolución y refleja el estado pendiente", async () => {
    iniciarSesion();
    let estadoDev = null;
    let bodyEnviado = null;
    server.use(
      http.get(`${API}/api/ventas/compras`, () =>
        HttpResponse.json([
          {
            id: 10, reserva_id: 60, total: 800, created_at: "2026-11-07T20:00:00Z",
            tickets: [
              {
                orden_item_id: 601, ticket_id: 201, evento_id: 1, zona_id: 20, tipo_zona: "general",
                fila: null, numero: null, precio: 800, evento_fecha_inicio: "2026-12-20T21:00:00Z",
                evento_cancelado: false, evento_estado: "activo", devolucion: estadoDev,
              },
            ],
          },
        ]),
      ),
      http.post(`${API}/api/ventas/devoluciones`, async ({ request }) => {
        bodyEnviado = await request.json();
        estadoDev = { id: 77, estado: "pendiente", motivo: bodyEnviado.motivo, nota_resolucion: null };
        return HttpResponse.json(estadoDev, { status: 201 });
      }),
    );

    const { user } = renderEn("/compras");
    await user.click(await screen.findByRole("button", { name: "Solicitar devolución" }));
    await user.type(screen.getByLabelText("Motivo (opcional)"), "No puedo ir");
    await user.click(screen.getByRole("button", { name: "Confirmar devolución" }));

    expect(await screen.findByText("Devolución pendiente")).toBeInTheDocument();
    expect(bodyEnviado).toEqual({ orden_item_id: 601, motivo: "No puedo ir" });
    expect(screen.queryByRole("button", { name: "Solicitar devolución" })).not.toBeInTheDocument();
  });

  test("muestra evento finalizado sin botón de devolución y evento cancelado con botón habilitado", async () => {
    iniciarSesion();
    server.use(
      http.get(`${API}/api/ventas/compras`, () =>
        HttpResponse.json([
          {
            id: 11, reserva_id: 61, total: 2300, created_at: "2026-11-07T20:00:00Z",
            tickets: [
              {
                orden_item_id: 701, ticket_id: 301, evento_id: 2, zona_id: 10, tipo_zona: "numerada",
                fila: "B", numero: 1, precio: 1500, evento_fecha_inicio: "2025-01-01T20:00:00Z",
                evento_cancelado: false, evento_estado: "finalizado", devolucion: null,
              },
              {
                orden_item_id: 702, ticket_id: 302, evento_id: 3, zona_id: 20, tipo_zona: "general",
                fila: null, numero: null, precio: 800, evento_fecha_inicio: "2025-01-01T20:00:00Z",
                evento_cancelado: true, evento_estado: "cancelado",
                devolucion: { id: 88, estado: "rechazada", motivo: "m", nota_resolucion: "Reenviar" },
              },
            ],
          },
        ]),
      ),
    );

    renderEn("/compras");
    expect(await screen.findByText(/Evento finalizado/)).toBeInTheDocument();
    expect(screen.getByText(/Evento cancelado/)).toBeInTheDocument();
    expect(screen.getByText("Devolución rechazada")).toBeInTheDocument();
    expect(screen.getByText("(Reenviar)")).toBeInTheDocument();
    // Solo el ticket del evento cancelado (con devolucion rechazada) puede solicitar devolucion.
    expect(screen.getAllByRole("button", { name: "Solicitar devolución" })).toHaveLength(1);
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
