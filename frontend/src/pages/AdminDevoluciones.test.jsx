import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { API, server } from "../test/server.js";
import { iniciarSesion, renderEn } from "../test/utilidades.jsx";

const SOLICITUD_BASE = {
  id: 1,
  orden_item_id: 501,
  orden_id: 9,
  ticket_id: 101,
  user_id: 20,
  evento_id: 1,
  zona_id: 10,
  tipo_zona: "numerada",
  fila: "A",
  numero: 1,
  precio: 1500,
  estado: "pendiente",
  motivo: "No puedo asistir",
  nota_resolucion: null,
  resuelto_por: null,
  resuelto_at: null,
  created_at: "2026-11-22T12:00:00Z",
  evento_fecha_inicio: "2026-12-20T21:00:00Z",
  evento_cancelado: true,
};

describe("gestión de devoluciones (admin)", () => {
  test("redirige al login sin sesión", async () => {
    renderEn("/admin/devoluciones");
    expect(await screen.findByRole("heading", { name: "Ingresar" })).toBeInTheDocument();
  });

  test("bloquea acceso a clientes y vuelve a la cartelera", async () => {
    iniciarSesion("cliente");
    server.use(
      http.get(`${API}/api/eventos`, () => HttpResponse.json([])),
      http.get(`${API}/api/eventos/tipos`, () => HttpResponse.json([])),
    );
    renderEn("/admin/devoluciones");
    expect(await screen.findByRole("heading", { name: "Cartelera" })).toBeInTheDocument();
  });

  test("administrador lista, ve evento cancelado y aprueba una solicitud", async () => {
    iniciarSesion("administrador");
    let lista = [SOLICITUD_BASE];
    let notaEnviada = null;
    server.use(
      http.get(`${API}/api/ventas/devoluciones`, ({ request }) => {
        const estado = new URL(request.url).searchParams.get("estado");
        return HttpResponse.json(estado ? lista.filter((d) => d.estado === estado) : lista);
      }),
      http.post(`${API}/api/ventas/devoluciones/1/aprobar`, async ({ request }) => {
        notaEnviada = (await request.json()).nota;
        lista = [{ ...SOLICITUD_BASE, estado: "aprobada", nota_resolucion: notaEnviada }];
        return HttpResponse.json(lista[0]);
      }),
    );

    const { user } = renderEn("/admin/devoluciones");
    expect(await screen.findByRole("heading", { name: "Gestión de devoluciones" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Devoluciones" })).toBeInTheDocument();
    expect(screen.getByText("Evento cancelado")).toBeInTheDocument();
    expect(screen.getByText(/Asiento A-1 · \$1500/)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Nota de resolución (opcional)"), "Aprobada por cancelación");
    await user.click(screen.getByRole("button", { name: "Aprobar" }));

    expect(await screen.findByText("Devolución #1 aprobada.")).toBeInTheDocument();
    expect(notaEnviada).toBe("Aprobada por cancelación");
    expect(screen.getByText("No hay solicitudes de devolución para el filtro seleccionado.")).toBeInTheDocument();
  });

  test("administrador rechaza solicitud y filtra por rechazadas", async () => {
    iniciarSesion("administrador");
    let lista = [{ ...SOLICITUD_BASE, id: 2, tipo_zona: "general", fila: null, numero: null, evento_cancelado: false }];
    server.use(
      http.get(`${API}/api/ventas/devoluciones`, ({ request }) => {
        const estado = new URL(request.url).searchParams.get("estado");
        return HttpResponse.json(estado ? lista.filter((d) => d.estado === estado) : lista);
      }),
      http.post(`${API}/api/ventas/devoluciones/2/rechazar`, async ({ request }) => {
        const nota = (await request.json()).nota;
        lista = [{ ...lista[0], estado: "rechazada", nota_resolucion: nota }];
        return HttpResponse.json(lista[0]);
      }),
    );

    const { user } = renderEn("/admin/devoluciones");
    expect(await screen.findByText(/Entrada general · \$1500/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nota de resolución (opcional)"), "Fuera de plazo");
    await user.click(screen.getByRole("button", { name: "Rechazar" }));

    expect(await screen.findByText("Devolución #2 rechazada.")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Filtrar por estado"), "rechazada");
    expect(await screen.findByText("Nota de resolución: Fuera de plazo")).toBeInTheDocument();
  });
});
