import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { API, server } from "./test/server.js";
import { renderEn } from "./test/utilidades.jsx";

test("muestra el encabezado y la cartelera en la portada", async () => {
  server.use(http.get(`${API}/api/eventos`, () => HttpResponse.json([])));
  renderEn("/");
  expect(screen.getByRole("link", { name: "Ticketera" })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "Cartelera" })).toBeInTheDocument();
});

test("si el refresh falla, el login avisa que la sesión se cerró (11.6)", async () => {
  const { iniciarSesion } = await import("./test/utilidades.jsx");
  iniciarSesion();
  server.use(
    http.get(`${API}/api/ventas/compras`, () => HttpResponse.json({ detail: "x" }, { status: 401 })),
    http.post(`${API}/api/auth/refresh`, () => HttpResponse.json({ detail: "x" }, { status: 401 })),
  );
  renderEn("/compras");
  expect(await screen.findByText("Tu sesión se cerró. Volvé a ingresar.")).toBeInTheDocument();
});

test("un logout manual no muestra el aviso de sesión cerrada", async () => {
  const { iniciarSesion } = await import("./test/utilidades.jsx");
  server.use(http.get(`${API}/api/eventos`, () => HttpResponse.json([])));
  iniciarSesion();
  const { user } = renderEn("/");
  await user.click(screen.getByRole("button", { name: "Salir" }));
  expect(screen.queryByText("Tu sesión se cerró. Volvé a ingresar.")).not.toBeInTheDocument();
});
