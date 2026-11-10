import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { tokensActuales } from "../api/client.js";
import { API, server } from "../test/server.js";
import { iniciarSesion, renderEn } from "../test/utilidades.jsx";

const PERFIL = {
  id: 20, email: "ana@example.com", rol: "cliente", estado: "activa", nombre: "Ana", apellido: "Pérez",
  dni: "30123456", fecha_nacimiento: "1990-05-17", telefono: "2215551234", calle: "Calle 7", numero: "1234",
  piso_depto: null, localidad: "La Plata", provincia: "Buenos Aires", codigo_postal: "1900",
  created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-05T10:00:00Z", last_login_at: "2026-11-09T10:00:00Z",
};

describe("perfil (11.4)", () => {
  test("muestra datos fijos, auditoría y permite editar", async () => {
    iniciarSesion();
    let enviado = null;
    server.use(
      http.get(`${API}/api/auth/perfil`, () => HttpResponse.json(PERFIL)),
      http.patch(`${API}/api/auth/perfil`, async ({ request }) => {
        enviado = await request.json();
        return HttpResponse.json({ ...PERFIL, ...enviado, updated_at: "2026-11-09T12:00:00Z" });
      }),
    );
    const { user } = renderEn("/perfil");
    expect(await screen.findByText("30123456")).toBeInTheDocument();
    expect(screen.getByText("ana@example.com")).toBeInTheDocument();
    expect(screen.getByText("Último ingreso")).toBeInTheDocument();

    const localidad = screen.getByLabelText("Localidad");
    await user.clear(localidad);
    await user.type(localidad, "Berisso");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText("Datos guardados.")).toBeInTheDocument();
    expect(enviado.localidad).toBe("Berisso");
    expect(enviado).not.toHaveProperty("email");
    expect(enviado).not.toHaveProperty("dni");
  });

  test("error de validación junto al campo", async () => {
    iniciarSesion();
    server.use(
      http.get(`${API}/api/auth/perfil`, () => HttpResponse.json(PERFIL)),
      http.patch(`${API}/api/auth/perfil`, () =>
        HttpResponse.json({ detail: [{ loc: ["body", "codigo_postal"], msg: "formato inválido" }] }, { status: 422 })),
    );
    const { user } = renderEn("/perfil");
    await user.click(await screen.findByRole("button", { name: "Guardar cambios" }));
    expect(await screen.findByText("formato inválido")).toBeInTheDocument();
  });
});

describe("cambio de contraseña (11.4)", () => {
  async function completar(user, actual = "tortuga-azul-42", nueva = "jirafa-violeta-77") {
    await user.type(screen.getByLabelText("Contraseña actual"), actual);
    await user.type(screen.getByLabelText("Contraseña nueva"), nueva);
    await user.type(screen.getByLabelText("Repetir contraseña nueva"), nueva);
    await user.click(screen.getByRole("button", { name: "Cambiar contraseña" }));
  }

  test("cambio exitoso guarda los tokens nuevos y mantiene la sesión", async () => {
    iniciarSesion();
    server.use(
      http.post(`${API}/api/auth/perfil/contrasenia`, () =>
        HttpResponse.json({ access_token: tokensActuales().access, refresh_token: "R-NUEVO", expires_in: 7200 })),
    );
    const { user } = renderEn("/perfil/contrasenia");
    await completar(user);
    expect(await screen.findByText(/Se cerraron tus otras sesiones/)).toBeInTheDocument();
    expect(tokensActuales().refresh).toBe("R-NUEVO");
    expect(screen.getByRole("link", { name: "Mi perfil" })).toBeInTheDocument();
  });

  test("contraseña actual incorrecta", async () => {
    iniciarSesion();
    server.use(
      http.post(`${API}/api/auth/perfil/contrasenia`, () => HttpResponse.json({ detail: "x" }, { status: 401 })),
    );
    const { user } = renderEn("/perfil/contrasenia");
    await completar(user, "no-es-la-actual");
    expect(await screen.findByText("La contraseña actual no es correcta.")).toBeInTheDocument();
    expect(tokensActuales().refresh).toBe("R1");
  });
});
