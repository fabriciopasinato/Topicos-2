import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { tokensActuales } from "../api/client.js";
import { API, server } from "../test/server.js";
import { renderEn, tokenFalso } from "../test/utilidades.jsx";

function cartelaVacia() {
  server.use(http.get(`${API}/api/eventos`, () => HttpResponse.json([])));
}

async function completar(user, email, password) {
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Contraseña"), password);
}

describe("login", () => {
  test("login exitoso guarda la sesión y vuelve a la cartelera", async () => {
    cartelaVacia();
    server.use(
      http.post(`${API}/api/auth/login`, () =>
        HttpResponse.json({ access_token: tokenFalso(), refresh_token: "R1", expires_in: 7200 }),
      ),
    );
    const { user } = renderEn("/login");
    await completar(user, "ana@example.com", "clave-segura-1");
    await user.click(screen.getByRole("button", { name: "Ingresar" }));

    expect(await screen.findByRole("heading", { name: "Cartelera" })).toBeInTheDocument();
    expect(tokensActuales()?.refresh).toBe("R1");
    expect(screen.getByRole("link", { name: "Mis compras" })).toBeInTheDocument();
  });

  test("credenciales inválidas (401)", async () => {
    server.use(
      http.post(`${API}/api/auth/login`, () => HttpResponse.json({ detail: "x" }, { status: 401 })),
    );
    const { user } = renderEn("/login");
    await completar(user, "ana@example.com", "otra-clave-1");
    await user.click(screen.getByRole("button", { name: "Ingresar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email o contraseña incorrectos.");
  });

  test("demasiados intentos (429) muestra el tiempo de espera", async () => {
    server.use(
      http.post(`${API}/api/auth/login`, () =>
        HttpResponse.json({ detail: "x" }, { status: 429, headers: { "Retry-After": "42" } }),
      ),
    );
    const { user } = renderEn("/login");
    await completar(user, "ana@example.com", "clave-segura-1");
    await user.click(screen.getByRole("button", { name: "Ingresar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("42 segundos");
  });
});

describe("registro", () => {
  test("registro exitoso lleva al login con aviso", async () => {
    server.use(
      http.post(`${API}/api/auth/registro`, () =>
        HttpResponse.json({ id: 1, email: "ana@example.com", rol: "cliente" }, { status: 201 }),
      ),
    );
    const { user } = renderEn("/registro");
    await completar(user, "ana@example.com", "clave-segura-1");
    await user.click(screen.getByRole("button", { name: "Registrarme" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Cuenta creada");
    expect(screen.getByRole("heading", { name: "Ingresar" })).toBeInTheDocument();
  });

  test("email ya registrado (409)", async () => {
    server.use(
      http.post(`${API}/api/auth/registro`, () => HttpResponse.json({ detail: "x" }, { status: 409 })),
    );
    const { user } = renderEn("/registro");
    await completar(user, "ana@example.com", "clave-segura-1");
    await user.click(screen.getByRole("button", { name: "Registrarme" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ese email ya está registrado.");
  });

  test("demasiados registros (429)", async () => {
    server.use(
      http.post(`${API}/api/auth/registro`, () =>
        HttpResponse.json({ detail: "x" }, { status: 429, headers: { "Retry-After": "9" } }),
      ),
    );
    const { user } = renderEn("/registro");
    await completar(user, "ana@example.com", "clave-segura-1");
    await user.click(screen.getByRole("button", { name: "Registrarme" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("9 segundos");
  });
});
