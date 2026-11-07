import { http, HttpResponse } from "msw";
import { describe, expect, test, vi } from "vitest";
import { API, server } from "../test/server.js";
import { api, ApiError, configurarAlFallarAuth, guardarTokens, mensajeDeError, tokensActuales } from "./client.js";

describe("cliente de API", () => {
  test("agrega el token de acceso", async () => {
    guardarTokens({ access_token: "A1", refresh_token: "R1" });
    server.use(
      http.get(`${API}/api/ventas/compras`, ({ request }) =>
        HttpResponse.json({ auth: request.headers.get("Authorization") }),
      ),
    );
    expect(await api("/api/ventas/compras")).toEqual({ auth: "Bearer A1" });
  });

  test("ante un 401 renueva el token y reintenta una sola vez", async () => {
    guardarTokens({ access_token: "viejo", refresh_token: "R1" });
    const llamadas = { compras: 0, refresh: 0 };
    server.use(
      http.get(`${API}/api/ventas/compras`, ({ request }) => {
        llamadas.compras += 1;
        return request.headers.get("Authorization") === "Bearer nuevo"
          ? HttpResponse.json([{ id: 1 }])
          : HttpResponse.json({ detail: "expirado" }, { status: 401 });
      }),
      http.post(`${API}/api/auth/refresh`, async ({ request }) => {
        llamadas.refresh += 1;
        expect(await request.json()).toEqual({ refresh_token: "R1" });
        return HttpResponse.json({ access_token: "nuevo", refresh_token: "R2" });
      }),
    );

    expect(await api("/api/ventas/compras")).toEqual([{ id: 1 }]);
    expect(llamadas).toEqual({ compras: 2, refresh: 1 });
    expect(tokensActuales()).toEqual({ access: "nuevo", refresh: "R2" });
  });

  test("si el refresh falla, borra la sesion y redirige al login", async () => {
    guardarTokens({ access_token: "viejo", refresh_token: "vencido" });
    const alFallar = vi.fn();
    configurarAlFallarAuth(alFallar);
    let compras = 0;
    server.use(
      http.get(`${API}/api/ventas/compras`, () => {
        compras += 1;
        return HttpResponse.json({ detail: "expirado" }, { status: 401 });
      }),
      http.post(`${API}/api/auth/refresh`, () => HttpResponse.json({ detail: "x" }, { status: 401 })),
    );

    await expect(api("/api/ventas/compras")).rejects.toMatchObject({ status: 401 });
    expect(compras).toBe(1);
    expect(alFallar).toHaveBeenCalledOnce();
    expect(tokensActuales()).toBeNull();
  });

  test("lanza ApiError con Retry-After en un 429", async () => {
    server.use(
      http.post(`${API}/api/auth/login`, () =>
        HttpResponse.json({ detail: "demasiadas" }, { status: 429, headers: { "Retry-After": "17" } }),
      ),
    );
    const error = await api("/api/auth/login", { method: "POST", body: {} }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.retryAfter).toBe(17);
    expect(mensajeDeError(error)).toMatch(/17 segundos/);
  });
});
