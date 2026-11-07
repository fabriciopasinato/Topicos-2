import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { API, server } from "../test/server.js";
import { DISPONIBILIDAD, EVENTO, iniciarSesion, renderEn } from "../test/utilidades.jsx";

function reserva(extra = {}) {
  return {
    id: 55,
    evento_id: 1,
    estado: "activa",
    hasta: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
    total: 2300,
    tickets: [
      { id: 101, zona_id: 10, tipo_zona: "numerada", fila: "A", numero: 1, precio: 1500 },
      { id: 201, zona_id: 20, tipo_zona: "general", fila: null, numero: null, precio: 800 },
    ],
    ...extra,
  };
}

describe("pago de la reserva", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    iniciarSesion();
  });
  afterEach(() => vi.useRealTimers());

  test("muestra los tickets y la cuenta regresiva", async () => {
    server.use(http.get(`${API}/api/ventas/reservas/55`, () => HttpResponse.json(reserva())));
    renderEn("/reservas/55");
    expect(await screen.findByText("Asiento A-1 · $1500")).toBeInTheDocument();
    expect(screen.getByText("Entrada general · $800")).toBeInTheDocument();
    expect(screen.getByText("5:00")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(61_000));
    expect(screen.getByText("3:59")).toBeInTheDocument();
  });

  test("pagar confirma la compra", async () => {
    server.use(
      http.get(`${API}/api/ventas/reservas/55`, () => HttpResponse.json(reserva())),
      http.post(`${API}/api/ventas/reservas/55/pago`, () =>
        HttpResponse.json({ id: 9, reserva_id: 55, total: 2300 }, { status: 201 }),
      ),
    );
    const { user } = renderEn("/reservas/55");
    await user.click(await screen.findByRole("button", { name: "Pagar" }));
    expect(await screen.findByRole("heading", { name: "¡Compra confirmada!" })).toBeInTheDocument();
    expect(screen.getByText("Total pagado: $2300")).toBeInTheDocument();
  });

  test("al terminar la cuenta regresiva avisa que venció", async () => {
    server.use(
      http.get(`${API}/api/ventas/reservas/55`, () =>
        HttpResponse.json(reserva({ hasta: new Date(Date.now() + 3000).toISOString() })),
      ),
    );
    renderEn("/reservas/55");
    await screen.findByRole("button", { name: "Pagar" });
    await act(() => vi.advanceTimersByTimeAsync(4000));
    expect(screen.getByRole("heading", { name: "La reserva venció" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a elegir" })).toHaveAttribute("href", "/eventos/1");
  });

  test("si el pago responde 409 avisa que venció", async () => {
    server.use(
      http.get(`${API}/api/ventas/reservas/55`, () => HttpResponse.json(reserva())),
      http.post(`${API}/api/ventas/reservas/55/pago`, () =>
        HttpResponse.json({ detail: "la reserva vencio" }, { status: 409 }),
      ),
    );
    const { user } = renderEn("/reservas/55");
    await user.click(await screen.findByRole("button", { name: "Pagar" }));
    expect(await screen.findByRole("heading", { name: "La reserva venció" })).toBeInTheDocument();
  });

  test("una reserva ya vencida se muestra como vencida", async () => {
    server.use(http.get(`${API}/api/ventas/reservas/55`, () => HttpResponse.json(reserva({ estado: "vencida" }))));
    renderEn("/reservas/55");
    expect(await screen.findByRole("heading", { name: "La reserva venció" })).toBeInTheDocument();
  });

  test("cancelar libera y vuelve al evento", async () => {
    let cancelada = false;
    server.use(
      http.get(`${API}/api/ventas/reservas/55`, () => HttpResponse.json(reserva())),
      http.delete(`${API}/api/ventas/reservas/55`, () => {
        cancelada = true;
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(`${API}/api/eventos/1`, () => HttpResponse.json(EVENTO)),
      http.get(`${API}/api/ventas/eventos/1/disponibilidad`, () => HttpResponse.json(DISPONIBILIDAD)),
    );
    const { user } = renderEn("/reservas/55");
    await user.click(await screen.findByRole("button", { name: "Cancelar reserva" }));
    expect(await screen.findByRole("heading", { name: "Recital de prueba" })).toBeInTheDocument();
    expect(cancelada).toBe(true);
  });
});
