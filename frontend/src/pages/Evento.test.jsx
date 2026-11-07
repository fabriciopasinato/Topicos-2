import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { API, server } from "../test/server.js";
import { DISPONIBILIDAD, EVENTO, iniciarSesion, renderEn } from "../test/utilidades.jsx";

function eventoYDisponibilidad(disponibilidad = DISPONIBILIDAD) {
  server.use(
    http.get(`${API}/api/eventos/1`, () => HttpResponse.json(EVENTO)),
    http.get(`${API}/api/ventas/eventos/1/disponibilidad`, () => HttpResponse.json(disponibilidad)),
  );
}

describe("cartelera y detalle", () => {
  test("la cartelera lista los eventos publicados", async () => {
    server.use(http.get(`${API}/api/eventos`, () => HttpResponse.json([EVENTO])));
    renderEn("/");
    const enlace = await screen.findByRole("link", { name: "Recital de prueba" });
    expect(enlace).toHaveAttribute("href", "/eventos/1");
    expect(screen.getByText("Estadio Central")).toBeInTheDocument();
  });

  test("cartelera vacía", async () => {
    server.use(http.get(`${API}/api/eventos`, () => HttpResponse.json([])));
    renderEn("/");
    expect(await screen.findByText("No hay eventos publicados por ahora.")).toBeInTheDocument();
  });

  test("el detalle muestra la disponibilidad que informa ventas", async () => {
    eventoYDisponibilidad();
    renderEn("/eventos/1");
    expect(await screen.findByRole("heading", { name: "Recital de prueba" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Asiento A-1" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Asiento A-3 no disponible" })).toBeDisabled();
    expect(screen.getByText(/10 disponibles/)).toBeInTheDocument();
  });
});

describe("reserva", () => {
  test("reserva de asientos elegidos con Idempotency-Key y paso al pago", async () => {
    iniciarSesion();
    eventoYDisponibilidad();
    let recibido = null;
    server.use(
      http.post(`${API}/api/ventas/reservas`, async ({ request }) => {
        recibido = { body: await request.json(), clave: request.headers.get("Idempotency-Key") };
        return HttpResponse.json({ id: 55 }, { status: 201 });
      }),
      http.get(`${API}/api/ventas/reservas/55`, () =>
        HttpResponse.json({ id: 55, evento_id: 1, estado: "activa", total: 0, tickets: [],
                            hasta: new Date(Date.now() + 300_000).toISOString() }),
      ),
    );
    const { user } = renderEn("/eventos/1");
    await user.click(await screen.findByRole("button", { name: "Asiento A-1" }));
    await user.click(screen.getByRole("button", { name: "Asiento A-2" }));
    await user.clear(screen.getByLabelText("Cantidad para Campo"));
    await user.type(screen.getByLabelText("Cantidad para Campo"), "2");
    await user.click(screen.getByRole("button", { name: "Reservar (4)" }));

    expect(await screen.findByRole("heading", { name: "Tu reserva" })).toBeInTheDocument();
    expect(recibido.body).toEqual({ evento_id: 1, asientos: [101, 102], generales: [{ zona_id: 20, cantidad: 2 }] });
    expect(recibido.clave).toBeTruthy();
  });

  test("un reintento reenvía la misma Idempotency-Key", async () => {
    iniciarSesion();
    eventoYDisponibilidad();
    const claves = [];
    server.use(
      http.post(`${API}/api/ventas/reservas`, ({ request }) => {
        claves.push(request.headers.get("Idempotency-Key"));
        return claves.length === 1
          ? HttpResponse.error() // falla de red
          : HttpResponse.json({ id: 56 }, { status: 201 });
      }),
      http.get(`${API}/api/ventas/reservas/56`, () =>
        HttpResponse.json({ id: 56, evento_id: 1, estado: "activa", total: 0, tickets: [],
                            hasta: new Date(Date.now() + 300_000).toISOString() }),
      ),
    );
    const { user } = renderEn("/eventos/1");
    await user.click(await screen.findByRole("button", { name: "Asiento A-1" }));
    await user.click(screen.getByRole("button", { name: "Reservar (1)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar");
    await user.click(screen.getByRole("button", { name: "Reservar (1)" }));

    await screen.findByRole("heading", { name: "Tu reserva" });
    expect(claves).toHaveLength(2);
    expect(claves[0]).toBe(claves[1]);
  });

  test("asiento tomado por otro (409) avisa y refresca la disponibilidad", async () => {
    iniciarSesion();
    let consultas = 0;
    server.use(
      http.get(`${API}/api/eventos/1`, () => HttpResponse.json(EVENTO)),
      http.get(`${API}/api/ventas/eventos/1/disponibilidad`, () => {
        consultas += 1;
        if (consultas === 1) return HttpResponse.json(DISPONIBILIDAD);
        const actualizada = structuredClone(DISPONIBILIDAD);
        actualizada.zonas[0].asientos[0].disponible = false;
        return HttpResponse.json(actualizada);
      }),
      http.post(`${API}/api/ventas/reservas`, () =>
        HttpResponse.json({ detail: "asientos no disponibles: A-1" }, { status: 409 }),
      ),
    );
    const { user } = renderEn("/eventos/1");
    await user.click(await screen.findByRole("button", { name: "Asiento A-1" }));
    await user.click(screen.getByRole("button", { name: "Reservar (1)" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("A-1");
    expect(await screen.findByRole("button", { name: "Asiento A-1 no disponible" })).toBeDisabled();
    expect(consultas).toBe(2);
  });

  test("más tickets que el máximo (422) muestra el motivo", async () => {
    iniciarSesion();
    eventoYDisponibilidad();
    server.use(
      http.post(`${API}/api/ventas/reservas`, () =>
        HttpResponse.json({ detail: "una reserva admite como maximo 10 tickets" }, { status: 422 }),
      ),
    );
    const { user } = renderEn("/eventos/1");
    await user.clear(await screen.findByLabelText("Cantidad para Campo"));
    await user.type(screen.getByLabelText("Cantidad para Campo"), "10");
    await user.click(screen.getByRole("button", { name: "Asiento A-1" }));
    await user.click(screen.getByRole("button", { name: "Reservar (11)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("10 tickets");
  });

  test("sin sesión, reservar lleva al login", async () => {
    eventoYDisponibilidad();
    const { user } = renderEn("/eventos/1");
    await user.click(await screen.findByRole("button", { name: "Asiento A-1" }));
    await user.click(screen.getByRole("button", { name: "Reservar (1)" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Ingresá para reservar.");
    expect(within(screen.getByRole("main")).getByRole("heading", { name: "Ingresar" })).toBeInTheDocument();
  });
});
