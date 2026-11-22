import { fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { API, server } from "../../test/server.js";
import { EVENTO, iniciarSesion, RECINTOS, renderEn, TIPOS } from "../../test/utilidades.jsx";

const BORRADOR = { ...EVENTO, id: 7, nombre: "Borrador de prueba", estado: "borrador", sectores: [] };

function catalogos() {
  server.use(
    http.get(`${API}/api/eventos/tipos`, () => HttpResponse.json(TIPOS)),
    http.get(`${API}/api/eventos/recintos`, () => HttpResponse.json(RECINTOS)),
  );
}

/** Registra GET del evento; `estado` se puede cambiar desde el test con `actual.evento = ...`. */
function eventoEnServidor(evento) {
  const actual = { evento };
  server.use(http.get(`${API}/api/eventos/${evento.id}`, () => HttpResponse.json(actual.evento)));
  return actual;
}

function capturar(metodo, ruta, respuesta) {
  const recibidos = [];
  server.use(
    http[metodo](`${API}${ruta}`, async ({ request }) => {
      recibidos.push(request.method === "DELETE" ? null : await request.json().catch(() => null));
      return typeof respuesta === "function" ? respuesta() : respuesta;
    }),
  );
  return recibidos;
}

describe("6.1 mis eventos", () => {
  test("lista los eventos del owner con su estado", async () => {
    iniciarSesion("event_owner");
    server.use(
      http.get(`${API}/api/eventos/mios`, () =>
        HttpResponse.json([
          { ...BORRADOR, operaciones_pendientes: [] },
          { ...EVENTO, id: 8, nombre: "Ya pasó", estado: "finalizado", operaciones_pendientes: [] },
        ]),
      ),
    );
    renderEn("/owner");
    expect(await screen.findByRole("link", { name: "Borrador de prueba" })).toHaveAttribute("href", "/owner/eventos/7");
    expect(screen.getByText("Borrador")).toBeInTheDocument();
    expect(screen.getByText("Finalizado")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mis eventos" })).toBeInTheDocument();
  });

  test("avisa las operaciones pendientes", async () => {
    iniciarSesion("event_owner");
    server.use(
      http.get(`${API}/api/eventos/mios`, () =>
        HttpResponse.json([{ ...EVENTO, operaciones_pendientes: [{ tipo: "cancelar", intentos: 2, created_at: "x" }] }]),
      ),
    );
    renderEn("/owner");
    expect(await screen.findByText(/Cancelación en proceso/)).toBeInTheDocument();
  });

  test("un cliente no accede: vuelve a la portada", async () => {
    iniciarSesion("cliente");
    server.use(http.get(`${API}/api/eventos`, () => HttpResponse.json([])), http.get(`${API}/api/eventos/tipos`, () => HttpResponse.json(TIPOS)));
    renderEn("/owner");
    expect(await screen.findByRole("heading", { name: "Cartelera" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Mis eventos" })).not.toBeInTheDocument();
  });
});

describe("6.2 alta y edicion", () => {
  test("alta con clasificacion y paso a la gestion del evento", async () => {
    iniciarSesion("event_owner");
    catalogos();
    const altas = capturar("post", "/api/eventos", HttpResponse.json(BORRADOR, { status: 201 }));
    eventoEnServidor(BORRADOR);
    const { user } = renderEn("/owner/eventos/nuevo");

    await user.type(await screen.findByLabelText("Nombre"), "Borrador de prueba");
    fireEvent.change(screen.getByLabelText("Fecha y hora de inicio"), { target: { value: "2030-01-10T21:00" } });
    await user.selectOptions(screen.getByLabelText("Tipo"), "recital");
    await user.selectOptions(screen.getByLabelText("Recinto"), "1");
    await user.type(screen.getByLabelText("Organizador"), "DF Entertainment");
    await user.type(screen.getByLabelText("Participantes (separados por coma)"), "Los Piojos, Ciro");
    await user.click(screen.getByRole("button", { name: "Crear evento" }));

    expect(await screen.findByRole("heading", { name: /Borrador de prueba/ })).toBeInTheDocument();
    expect(altas[0]).toMatchObject({
      nombre: "Borrador de prueba", tipo: "recital", recinto_id: 1, organizador: "DF Entertainment",
      participantes: ["Los Piojos", "Ciro"], fecha: new Date("2030-01-10T21:00").toISOString(),
    });
  });

  test("muestra el 422 del backend", async () => {
    iniciarSesion("event_owner");
    catalogos();
    capturar("post", "/api/eventos", HttpResponse.json({ detail: "el tipo de evento 'x' no existe" }, { status: 422 }));
    const { user } = renderEn("/owner/eventos/nuevo");
    await user.type(await screen.findByLabelText("Nombre"), "X");
    fireEvent.change(screen.getByLabelText("Fecha y hora de inicio"), { target: { value: "2030-01-10T21:00" } });
    await user.selectOptions(screen.getByLabelText("Tipo"), "recital");
    await user.selectOptions(screen.getByLabelText("Recinto"), "1");
    await user.type(screen.getByLabelText("Organizador"), "DF");
    await user.click(screen.getByRole("button", { name: "Crear evento" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("el tipo de evento 'x' no existe");
  });

  test("alta de un recinto desde el formulario", async () => {
    iniciarSesion("event_owner");
    catalogos();
    capturar("post", "/api/eventos/recintos", HttpResponse.json({ id: 2, nombre: "Teatro Nuevo", direccion: "" }, { status: 201 }));
    const { user } = renderEn("/owner/eventos/nuevo");
    await user.click(await screen.findByRole("button", { name: "Agregar un recinto" }));
    await user.type(screen.getByLabelText("Nombre del recinto"), "Teatro Nuevo");
    await user.click(screen.getByRole("button", { name: "Guardar recinto" }));
    expect(await screen.findByRole("option", { name: "Teatro Nuevo" })).toBeInTheDocument();
    expect(screen.getByLabelText("Recinto")).toHaveValue("2");
  });

  test("edicion de un evento publicado: sin fecha y con el recinto bloqueado", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(EVENTO);
    const cambios = capturar("patch", "/api/eventos/1", HttpResponse.json({ ...EVENTO, descripcion: "Con invitados" }));
    const { user } = renderEn("/owner/eventos/1");

    const descripcion = await screen.findByLabelText("Descripción");
    expect(screen.queryByLabelText("Fecha y hora de inicio")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Recinto")).toBeDisabled();
    await user.type(descripcion, "Con invitados");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText("Cambios guardados.")).toBeInTheDocument();
    expect(cambios[0]).toMatchObject({ descripcion: "Con invitados" });
    expect(cambios[0]).not.toHaveProperty("recinto_id");
    expect(cambios[0]).not.toHaveProperty("fecha");
  });

  test("muestra el 409 de la edicion", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(EVENTO);
    capturar("patch", "/api/eventos/1", HttpResponse.json({ detail: "el evento tiene una cancelacion pendiente" }, { status: 409 }));
    const { user } = renderEn("/owner/eventos/1");
    await user.click(await screen.findByRole("button", { name: "Guardar cambios" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cancelacion pendiente");
  });
});

describe("6.3 zonas y publicacion", () => {
  const CON_SECTOR = { ...BORRADOR, sectores: [{ id: 3, nombre: "Platea", zonas: [{ id: 30, nombre: "Campo", tipo: "general", capacidad: 100, precio: 800, asientos: [] }] }] };

  test("agrega un sector", async () => {
    iniciarSesion("event_owner");
    catalogos();
    const servidor = eventoEnServidor(BORRADOR);
    const altas = capturar("post", "/api/eventos/7/sectores", () => {
      servidor.evento = { ...BORRADOR, sectores: [{ id: 3, nombre: "Platea", zonas: [] }] };
      return HttpResponse.json({ id: 3, nombre: "Platea", zonas: [] }, { status: 201 });
    });
    const { user } = renderEn("/owner/eventos/7");
    await user.type(await screen.findByLabelText("Nuevo sector"), "Platea");
    await user.click(screen.getByRole("button", { name: "Agregar sector" }));
    expect(await screen.findByRole("heading", { name: "Platea" })).toBeInTheDocument();
    expect(altas[0]).toEqual({ nombre: "Platea" });
  });

  test("agrega una zona numerada con filas y asientos por fila", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(CON_SECTOR);
    const altas = capturar("post", "/api/eventos/7/sectores/3/zonas", HttpResponse.json({ id: 31 }, { status: 201 }));
    const { user } = renderEn("/owner/eventos/7");
    const zona = within(await screen.findByRole("group", { name: "Agregar zona" }));
    await user.type(zona.getByLabelText("Nombre de la zona"), "Platea A");
    await user.selectOptions(zona.getByLabelText("Tipo de zona"), "numerada");
    await user.type(zona.getByLabelText("Precio"), "1500");
    await user.type(zona.getByLabelText("Filas (separadas por coma)"), "A, B, C");
    await user.type(zona.getByLabelText("Asientos por fila"), "10");
    await user.click(zona.getByRole("button", { name: "Agregar zona" }));
    await screen.findByRole("heading", { name: "Platea" });
    expect(altas[0]).toEqual({ nombre: "Platea A", tipo: "numerada", precio: "1500", filas: ["A", "B", "C"], asientos_por_fila: 10 });
  });

  test("muestra el 422 de una zona invalida", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(CON_SECTOR);
    capturar("post", "/api/eventos/7/sectores/3/zonas", HttpResponse.json({ detail: [{ msg: "capacidad" }] }, { status: 422 }));
    const { user } = renderEn("/owner/eventos/7");
    const zona = within(await screen.findByRole("group", { name: "Agregar zona" }));
    await user.type(zona.getByLabelText("Nombre de la zona"), "Z");
    await user.type(zona.getByLabelText("Precio"), "10");
    await user.type(zona.getByLabelText("Capacidad"), "0");
    await user.click(zona.getByRole("button", { name: "Agregar zona" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Revisá la zona");
  });

  test("borra una zona del borrador", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(CON_SECTOR);
    const bajas = capturar("delete", "/api/eventos/7/zonas/30", new HttpResponse(null, { status: 204 }));
    const { user } = renderEn("/owner/eventos/7");
    await user.click(await screen.findByRole("button", { name: "Borrar zona Campo" }));
    await screen.findByRole("heading", { name: "Platea" });
    expect(bajas).toHaveLength(1);
  });

  test("publica y oculta la edicion de zonas", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(CON_SECTOR);
    capturar("post", "/api/eventos/7/publicar", HttpResponse.json({ ...CON_SECTOR, estado: "publicado" }));
    const { user } = renderEn("/owner/eventos/7");
    await user.click(await screen.findByRole("button", { name: "Publicar" }));
    expect(await screen.findByText("Evento publicado.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Borrar zona Campo" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publicar" })).not.toBeInTheDocument();
  });

  test("ventas caido al publicar (503): el evento sigue en borrador", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(CON_SECTOR);
    capturar("post", "/api/eventos/7/publicar", HttpResponse.json({ detail: "ventas no disponible: el evento sigue en borrador" }, { status: 503 }));
    const { user } = renderEn("/owner/eventos/7");
    await user.click(await screen.findByRole("button", { name: "Publicar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ventas no disponible");
    expect(screen.getByRole("button", { name: "Publicar" })).toBeInTheDocument();
  });

  test("publicacion sin zonas (422)", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(BORRADOR);
    capturar("post", "/api/eventos/7/publicar", HttpResponse.json({ detail: "el evento no tiene zonas" }, { status: 422 }));
    const { user } = renderEn("/owner/eventos/7");
    await user.click(await screen.findByRole("button", { name: "Publicar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("el evento no tiene zonas");
  });
});

describe("6.4 reprogramar, cancelar y borrar", () => {
  const PENDIENTE = (tipo) => [{ tipo, intentos: 1, created_at: "2030-01-01T00:00:00Z" }];

  test("reprogramacion aplicada", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(EVENTO);
    const pedidos = capturar("post", "/api/eventos/1/reprogramar", HttpResponse.json({ ...EVENTO, fecha: "2030-02-01T21:00:00Z" }));
    const { user } = renderEn("/owner/eventos/1");
    fireEvent.change(await screen.findByLabelText("Nueva fecha y hora"), { target: { value: "2030-02-01T18:00" } });
    await user.click(screen.getByRole("button", { name: "Reprogramar" }));
    expect(await screen.findByText("Evento reprogramado.")).toBeInTheDocument();
    expect(pedidos[0]).toEqual({ fecha: new Date("2030-02-01T18:00").toISOString() });
  });

  test("reprogramacion en proceso (202)", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(EVENTO);
    capturar("post", "/api/eventos/1/reprogramar", HttpResponse.json({ ...EVENTO, operaciones_pendientes: PENDIENTE("reprogramar") }, { status: 202 }));
    const { user } = renderEn("/owner/eventos/1");
    fireEvent.change(await screen.findByLabelText("Nueva fecha y hora"), { target: { value: "2030-02-01T18:00" } });
    await user.click(screen.getByRole("button", { name: "Reprogramar" }));
    expect(await screen.findByText(/La reprogramación está en proceso/)).toBeInTheDocument();
  });

  test("cancelacion con confirmacion", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(EVENTO);
    const pedidos = capturar("post", "/api/eventos/1/cancelar", HttpResponse.json({ ...EVENTO, estado: "cancelado" }));
    const { user } = renderEn("/owner/eventos/1");
    await user.click(await screen.findByRole("button", { name: "Cancelar evento" }));
    expect(pedidos).toHaveLength(0); // todavia no: pide confirmacion
    await user.click(screen.getByRole("button", { name: "Sí, cancelar evento" }));
    expect(await screen.findByText("Evento cancelado.")).toBeInTheDocument();
    expect(pedidos).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Reprogramar" })).not.toBeInTheDocument();
  });

  test("cancelacion en proceso (202)", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(EVENTO);
    capturar("post", "/api/eventos/1/cancelar", HttpResponse.json({ ...EVENTO, operaciones_pendientes: PENDIENTE("cancelar") }, { status: 202 }));
    const { user } = renderEn("/owner/eventos/1");
    await user.click(await screen.findByRole("button", { name: "Cancelar evento" }));
    await user.click(screen.getByRole("button", { name: "Sí, cancelar evento" }));
    expect(await screen.findByText(/La cancelación está en proceso/)).toBeInTheDocument();
  });

  test("arrepentirse de cancelar no envia nada", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(EVENTO);
    const pedidos = capturar("post", "/api/eventos/1/cancelar", HttpResponse.json(EVENTO));
    const { user } = renderEn("/owner/eventos/1");
    await user.click(await screen.findByRole("button", { name: "Cancelar evento" }));
    await user.click(screen.getByRole("button", { name: "No" }));
    expect(pedidos).toHaveLength(0);
  });

  test("borrar un borrador vuelve a mis eventos", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor(BORRADOR);
    const bajas = capturar("delete", "/api/eventos/7", new HttpResponse(null, { status: 204 }));
    server.use(http.get(`${API}/api/eventos/mios`, () => HttpResponse.json([])));
    const { user } = renderEn("/owner/eventos/7");
    await user.click(await screen.findByRole("button", { name: "Borrar borrador" }));
    await user.click(screen.getByRole("button", { name: "Sí, borrar borrador" }));
    expect(await screen.findByRole("heading", { name: "Mis eventos" })).toBeInTheDocument();
    expect(bajas).toHaveLength(1);
  });

  test("un evento cancelado no ofrece acciones", async () => {
    iniciarSesion("event_owner");
    catalogos();
    eventoEnServidor({ ...EVENTO, estado: "cancelado" });
    renderEn("/owner/eventos/1");
    expect(await screen.findByText("Cancelado")).toBeInTheDocument();
    for (const nombre of ["Publicar", "Cancelar evento", "Reprogramar", "Guardar cambios"]) {
      expect(screen.queryByRole("button", { name: nombre })).not.toBeInTheDocument();
    }
  });
});
