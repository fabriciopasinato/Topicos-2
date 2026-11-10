import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { tokensActuales } from "../api/client.js";
import { API, server } from "../test/server.js";
import { renderEn, tokenFalso } from "../test/utilidades.jsx";

async function completarLogin(user, email = "ana@example.com", password = "tortuga-azul-42") {
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Contraseña"), password);
  await user.click(screen.getByRole("button", { name: "Ingresar" }));
}

function loginResponde(status, cuerpo, headers = {}) {
  server.use(http.post(`${API}/api/auth/login`, () => HttpResponse.json(cuerpo, { status, headers })));
}

describe("login (11.2)", () => {
  test("login exitoso guarda la sesión y vuelve a la cartelera", async () => {
    server.use(http.get(`${API}/api/eventos`, () => HttpResponse.json([])));
    loginResponde(200, { access_token: tokenFalso(), refresh_token: "R1", expires_in: 7200 });
    const { user } = renderEn("/login");
    await completarLogin(user);
    expect(await screen.findByRole("heading", { name: "Cartelera" })).toBeInTheDocument();
    expect(tokensActuales()?.refresh).toBe("R1");
    expect(screen.getByRole("link", { name: "Mi perfil" })).toBeInTheDocument();
  });

  test("credenciales inválidas", async () => {
    loginResponde(401, { detail: "x", codigo: "credenciales_invalidas" });
    const { user } = renderEn("/login");
    await completarLogin(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Email o contraseña incorrectos.");
    expect(screen.queryByRole("button", { name: /Reenviar/ })).not.toBeInTheDocument();
  });

  test("email no verificado ofrece reenviar la verificación", async () => {
    let reenviado = null;
    loginResponde(403, { detail: "Tenés que verificar tu email antes de ingresar.", codigo: "email_no_verificado" });
    server.use(
      http.post(`${API}/api/auth/reenviar-verificacion`, async ({ request }) => {
        reenviado = await request.json();
        return HttpResponse.json({ detail: "ok" }, { status: 202 });
      }),
    );
    const { user } = renderEn("/login");
    await completarLogin(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("verificar tu email");
    await user.click(screen.getByRole("button", { name: "Reenviar email de verificación" }));
    expect(await screen.findByText("Te enviamos un nuevo email de verificación.")).toBeInTheDocument();
    expect(reenviado).toEqual({ email: "ana@example.com" });
  });

  test("cuenta bloqueada indica revisar el email", async () => {
    loginResponde(403, {
      detail: "Tu cuenta está bloqueada. Revisá tu email para restablecer la contraseña.",
      codigo: "cuenta_bloqueada",
    });
    const { user } = renderEn("/login");
    await completarLogin(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Tu cuenta está bloqueada");
  });

  test("demasiados intentos (429) muestra el tiempo de espera", async () => {
    loginResponde(429, { detail: "x" }, { "Retry-After": "42" });
    const { user } = renderEn("/login");
    await completarLogin(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("42 segundos");
  });

  test("tiene el link a olvidé mi contraseña", async () => {
    renderEn("/login");
    expect(screen.getByRole("link", { name: "Olvidé mi contraseña" })).toHaveAttribute("href", "/olvide");
  });
});

// --- Registro (11.1) ------------------------------------------------------------

const DATOS = {
  Nombre: "Ana", Apellido: "Pérez", DNI: "30123456", "Fecha de nacimiento": "1990-05-17",
  "Teléfono": "2215551234", Calle: "Calle 7", "Número": "1234", Localidad: "La Plata",
  "Código postal": "1900", Email: "ana@example.com",
};

async function completarRegistro(user, { password = "tortuga-azul-42", repetida = password, ...cambios } = {}) {
  for (const [label, valor] of Object.entries({ ...DATOS, ...cambios })) {
    const campo = screen.getByLabelText(label);
    await user.clear(campo);
    if (valor) await user.type(campo, valor);
  }
  await user.selectOptions(screen.getByLabelText("Provincia"), "Buenos Aires");
  await user.type(screen.getByLabelText("Contraseña"), password);
  await user.type(screen.getByLabelText("Repetir contraseña"), repetida);
}

describe("registro (11.1)", () => {
  test("registro exitoso envía todos los datos y pide revisar el email", async () => {
    let recibido = null;
    server.use(
      http.post(`${API}/api/auth/registro`, async ({ request }) => {
        recibido = await request.json();
        return HttpResponse.json({ id: 1, email: "ana@example.com", rol: "cliente" }, { status: 201 });
      }),
    );
    const { user } = renderEn("/registro");
    await completarRegistro(user);
    await user.click(screen.getByRole("button", { name: "Registrarme" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Te enviamos un email a ana@example.com");
    expect(recibido).toMatchObject({
      email: "ana@example.com", password: "tortuga-azul-42", dni: "30123456", provincia: "Buenos Aires",
      localidad: "La Plata", codigo_postal: "1900", fecha_nacimiento: "1990-05-17", piso_depto: null,
    });
    expect(recibido).not.toHaveProperty("repetida");
  });

  test("contraseñas que no coinciden no se envían", async () => {
    const { user } = renderEn("/registro");
    await completarRegistro(user, { repetida: "otra-cosa-distinta" });
    expect(screen.getByText("Las contraseñas no coinciden.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registrarme" })).toBeDisabled();
  });

  test("contraseña corta se marca en vivo", async () => {
    const { user } = renderEn("/registro");
    await user.type(screen.getByLabelText("Contraseña"), "corta");
    expect(screen.getByText("Mínimo 10 caracteres.")).toBeInTheDocument();
  });

  test("DNI con letras se marca en vivo", async () => {
    const { user } = renderEn("/registro");
    await user.type(screen.getByLabelText("DNI"), "30A");
    expect(screen.getByText(/7 u 8 números/)).toBeInTheDocument();
  });

  test("DNI duplicado (409)", async () => {
    server.use(
      http.post(`${API}/api/auth/registro`, () =>
        HttpResponse.json({ detail: "El DNI ya está registrado." }, { status: 409 }),
      ),
    );
    const { user } = renderEn("/registro");
    await completarRegistro(user);
    await user.click(screen.getByRole("button", { name: "Registrarme" }));
    expect(await screen.findByText("El DNI ya está registrado.")).toBeInTheDocument();
  });

  test("el error de campo del backend se muestra junto al campo", async () => {
    server.use(
      http.post(`${API}/api/auth/registro`, () =>
        HttpResponse.json(
          { detail: [{ loc: ["body", "password"], msg: "La contraseña es demasiado común. Elegí otra." }] },
          { status: 422 },
        ),
      ),
    );
    const { user } = renderEn("/registro");
    await completarRegistro(user, { password: "password1234" });
    await user.click(screen.getByRole("button", { name: "Registrarme" }));
    const campo = screen.getByLabelText("Contraseña");
    expect(await screen.findByText("La contraseña es demasiado común. Elegí otra.")).toBeInTheDocument();
    expect(campo).toHaveAttribute("aria-invalid", "true");
  });
});
