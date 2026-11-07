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
