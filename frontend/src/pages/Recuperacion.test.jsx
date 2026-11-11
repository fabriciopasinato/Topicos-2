import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { API, server } from "../test/server.js";
import { renderEn } from "../test/utilidades.jsx";

describe("verificación de email (11.3)", () => {
  test("token válido verifica la cuenta (una sola llamada)", async () => {
    let llamadas = 0;
    server.use(
      http.post(`${API}/api/auth/verificar-email`, async ({ request }) => {
        llamadas += 1;
        expect(await request.json()).toEqual({ token: "abc" });
        return HttpResponse.json({ detail: "ok" });
      }),
    );
    renderEn("/verificar?token=abc");
    expect(await screen.findByRole("heading", { name: "¡Cuenta verificada!" })).toBeInTheDocument();
    expect(llamadas).toBe(1);
  });

  test("token vencido", async () => {
    server.use(http.post(`${API}/api/auth/verificar-email`, () => HttpResponse.json({ detail: "x" }, { status: 400 })));
    renderEn("/verificar?token=viejo");
    expect(await screen.findByRole("heading", { name: "El link no es válido" })).toBeInTheDocument();
  });

  test("sin token", () => {
    renderEn("/verificar");
    expect(screen.getByRole("heading", { name: "El link no es válido" })).toBeInTheDocument();
  });
});

describe("olvidé mi contraseña (11.3)", () => {
  test("muestra el mismo mensaje exista o no el email", async () => {
    let pedido = null;
    server.use(
      http.post(`${API}/api/auth/olvide-contrasenia`, async ({ request }) => {
        pedido = await request.json();
        return HttpResponse.json({ detail: "x" }, { status: 202 });
      }),
    );
    const { user } = renderEn("/olvide");
    await user.type(screen.getByLabelText("Email"), "nadie@example.com");
    await user.click(screen.getByRole("button", { name: "Enviarme el link" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Si nadie@example.com está registrado");
    expect(pedido).toEqual({ email: "nadie@example.com" });
  });
});

describe("restablecer contraseña (11.3)", () => {
  async function completar(user, contrasenia = "jirafa-violeta-77", repetida = contrasenia) {
    await user.type(screen.getByLabelText("Contraseña nueva"), contrasenia);
    await user.type(screen.getByLabelText("Repetir contraseña"), repetida);
  }

  test("restablecimiento exitoso lleva al login con aviso", async () => {
    let recibido = null;
    server.use(
      http.post(`${API}/api/auth/restablecer-contrasenia`, async ({ request }) => {
        recibido = await request.json();
        return HttpResponse.json({ detail: "ok" });
      }),
    );
    const { user } = renderEn("/restablecer?token=xyz");
    await completar(user);
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Contraseña actualizada");
    expect(screen.getByRole("heading", { name: "Ingresar" })).toBeInTheDocument();
    expect(recibido).toEqual({ token: "xyz", contrasenia: "jirafa-violeta-77" });
  });

  test("token vencido ofrece pedir otro link", async () => {
    server.use(
      http.post(`${API}/api/auth/restablecer-contrasenia`, () => HttpResponse.json({ detail: "x" }, { status: 400 })),
    );
    const { user } = renderEn("/restablecer?token=viejo");
    await completar(user);
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));
    expect(await screen.findByRole("link", { name: "Pedir otro link" })).toHaveAttribute("href", "/olvide");
  });

  test("contraseñas que no coinciden", async () => {
    const { user } = renderEn("/restablecer?token=xyz");
    await completar(user, "jirafa-violeta-77", "jirafa-violeta-78");
    expect(screen.getByText("Las contraseñas no coinciden.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar contraseña" })).toBeDisabled();
  });

  test("error de política del backend junto al campo", async () => {
    server.use(
      http.post(`${API}/api/auth/restablecer-contrasenia`, () =>
        HttpResponse.json({ detail: [{ loc: ["body", "contrasenia"], msg: "La contraseña es demasiado común. Elegí otra." }] },
          { status: 422 }),
      ),
    );
    const { user } = renderEn("/restablecer?token=xyz");
    await completar(user, "password12345");
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));
    expect(await screen.findByText("La contraseña es demasiado común. Elegí otra.")).toBeInTheDocument();
  });
});
