import { screen, waitFor } from "@testing-library/react";
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

  test("descarta respuestas lentas de un filtro anterior", async () => {
    iniciarSesion("administrador");
    let resolverPendientes;
    const esperaPendientes = new Promise((res) => {
      resolverPendientes = res;
    });

    server.use(
      http.get(`${API}/api/ventas/devoluciones`, async ({ request }) => {
        const estado = new URL(request.url).searchParams.get("estado");
        if (estado === "pendiente") {
          await esperaPendientes;
          return HttpResponse.json([{ ...SOLICITUD_BASE, id: 10, motivo: "Solicitud obsoleta" }]);
        }
        return HttpResponse.json([{ ...SOLICITUD_BASE, id: 20, estado: "aprobada", motivo: "Solicitud aprobada" }]);
      }),
    );

    const { user } = renderEn("/admin/devoluciones");
    expect(screen.getByText("Cargando devoluciones…")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Filtrar por estado"), "aprobada");
    expect(await screen.findByText("Motivo del cliente: Solicitud aprobada")).toBeInTheDocument();

    resolverPendientes();
    await new Promise((r) => setTimeout(r, 20));

    expect(screen.getByText("Motivo del cliente: Solicitud aprobada")).toBeInTheDocument();
    expect(screen.queryByText("Motivo del cliente: Solicitud obsoleta")).not.toBeInTheDocument();
  });

  test("resolver recarga con el filtro actual si el admin cambió de filtro mientras el POST estaba en vuelo", async () => {
    iniciarSesion("administrador");
    let resolverPost;
    const esperaPost = new Promise((res) => {
      resolverPost = res;
    });
    const consultas = [];

    server.use(
      http.get(`${API}/api/ventas/devoluciones`, ({ request }) => {
        const estado = new URL(request.url).searchParams.get("estado");
        consultas.push(estado);
        if (estado === "pendiente") {
          return HttpResponse.json([SOLICITUD_BASE]);
        }
        if (estado === "rechazada") {
          return HttpResponse.json([{ ...SOLICITUD_BASE, id: 9, estado: "rechazada", motivo: "Ya rechazada" }]);
        }
        return HttpResponse.json([]);
      }),
      http.post(`${API}/api/ventas/devoluciones/1/aprobar`, async () => {
        await esperaPost;
        return HttpResponse.json({ ...SOLICITUD_BASE, estado: "aprobada" });
      }),
    );

    const { user } = renderEn("/admin/devoluciones");
    expect(await screen.findByText("Solicitud #1 · pendiente")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Aprobar" }));
    await user.selectOptions(screen.getByLabelText("Filtrar por estado"), "rechazada");
    expect(await screen.findByText("Solicitud #9 · rechazada")).toBeInTheDocument();

    resolverPost();
    expect(await screen.findByText("Devolución #1 aprobada.")).toBeInTheDocument();

    expect(consultas).toEqual(["pendiente", "rechazada", "rechazada"]);
    expect(screen.getByText("Solicitud #9 · rechazada")).toBeInTheDocument();
    expect(screen.queryByText("Solicitud #1 · pendiente")).not.toBeInTheDocument();
  });

  test("mantiene deshabilitados los botones de la segunda solicitud si la primera termina antes", async () => {
    iniciarSesion("administrador");
    let resolverUno;
    let resolverDos;
    const esperaUno = new Promise((res) => {
      resolverUno = res;
    });
    const esperaDos = new Promise((res) => {
      resolverDos = res;
    });

    server.use(
      http.get(`${API}/api/ventas/devoluciones`, () =>
        HttpResponse.json([
          { ...SOLICITUD_BASE, id: 1 },
          { ...SOLICITUD_BASE, id: 2, orden_item_id: 502, ticket_id: 102, numero: 2 },
        ]),
      ),
      http.post(`${API}/api/ventas/devoluciones/1/aprobar`, async () => {
        await esperaUno;
        return HttpResponse.json({ ...SOLICITUD_BASE, id: 1, estado: "aprobada" });
      }),
      http.post(`${API}/api/ventas/devoluciones/2/aprobar`, async () => {
        await esperaDos;
        return HttpResponse.json({ ...SOLICITUD_BASE, id: 2, estado: "aprobada" });
      }),
    );

    const { user } = renderEn("/admin/devoluciones");
    expect(await screen.findByText("Solicitud #1 · pendiente")).toBeInTheDocument();

    const botonesAprobar = screen.getAllByRole("button", { name: "Aprobar" });
    const botonesRechazar = screen.getAllByRole("button", { name: "Rechazar" });

    await user.click(botonesAprobar[0]);
    await user.click(botonesAprobar[1]);

    expect(botonesAprobar[0]).toBeDisabled();
    expect(botonesAprobar[1]).toBeDisabled();
    expect(botonesRechazar[1]).toBeDisabled();

    resolverUno();
    expect(await screen.findByText("Devolución #1 aprobada.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Aprobar" })[0]).toBeEnabled());

    // La solicitud #2 sigue en vuelo: sus botones deben seguir deshabilitados.
    expect(screen.getAllByRole("button", { name: "Aprobar" })[1]).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Rechazar" })[1]).toBeDisabled();

    resolverDos();
    expect(await screen.findByText("Devolución #2 aprobada.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Aprobar" })[1]).toBeEnabled());
  });
});
