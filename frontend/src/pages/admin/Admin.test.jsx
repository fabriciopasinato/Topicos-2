import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { API, server } from "../../test/server.js";
import { iniciarSesion, renderEn } from "../../test/utilidades.jsx";

function cuenta(i, extra = {}) {
  return {
    id: i, email: `user${i}@x.com`, rol: "cliente", estado: "activa", nombre: "N", apellido: `Apellido${i}`,
    dni: `2000000${i}`, fecha_nacimiento: null, telefono: null, calle: null, numero: null, piso_depto: null,
    localidad: null, provincia: null, codigo_postal: null, motivo_bloqueo: null, intentos_fallidos: 0,
    created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-01T10:00:00Z", last_login_at: null, ...extra,
  };
}

describe("administración de cuentas (11.5)", () => {
  test("lista, busca y pagina", async () => {
    iniciarSesion("administrador");
    const pedidos = [];
    server.use(
      http.get(`${API}/api/auth/admin/usuarios`, ({ request }) => {
        const url = new URL(request.url);
        pedidos.push(Object.fromEntries(url.searchParams));
        const pagina = Number(url.searchParams.get("pagina"));
        const items = url.searchParams.get("q") ? [cuenta(7)] : Array.from({ length: 20 }, (_, i) => cuenta(i + (pagina - 1) * 20));
        return HttpResponse.json({ items, total: url.searchParams.get("q") ? 1 : 30, pagina, tamanio: 20 });
      }),
    );
    const { user } = renderEn("/admin/usuarios");
    expect(await screen.findByText("30 cuenta(s)")).toBeInTheDocument();
    expect(screen.getByText("Página 1 de 2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(await screen.findByText("Página 2 de 2")).toBeInTheDocument();
    expect(pedidos.at(-1).pagina).toBe("2");

    await user.type(screen.getByLabelText("Buscar"), "perez");
    await user.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByText("1 cuenta(s)")).toBeInTheDocument();
    expect(pedidos.at(-1)).toMatchObject({ q: "perez", pagina: "1" });
  });

  test("detalle con estado y auditoría; restablecer pide confirmación", async () => {
    iniciarSesion("administrador");
    let restablecida = false;
    server.use(
      http.get(`${API}/api/auth/admin/usuarios/7`, () =>
        HttpResponse.json(cuenta(7, restablecida
          ? { estado: "bloqueada", motivo_bloqueo: "restablecimiento_admin" }
          : { intentos_fallidos: 2, last_login_at: "2026-11-09T10:00:00Z" }))),
      http.post(`${API}/api/auth/admin/usuarios/7/restablecer-contrasenia`, () => {
        restablecida = true;
        return HttpResponse.json({ detail: "ok" }, { status: 202 });
      }),
    );
    const { user } = renderEn("/admin/usuarios/7");
    expect(await screen.findByRole("heading", { name: "user7@x.com" })).toBeInTheDocument();
    expect(screen.getByText("Intentos fallidos").nextSibling).toHaveTextContent("2");

    await user.click(screen.getByRole("button", { name: "Restablecer contraseña" }));
    expect(restablecida).toBe(false);  // primero pide confirmar
    await user.click(screen.getByRole("button", { name: "Sí, restablecer" }));
    expect(await screen.findByText(/le enviamos un email/)).toBeInTheDocument();
    expect(await screen.findByText(/Contraseña restablecida por un administrador/)).toBeInTheDocument();
  });

  test("alta de organizador", async () => {
    iniciarSesion("administrador");
    server.use(
      http.post(`${API}/api/auth/event-owners`, async ({ request }) => {
        const datos = await request.json();
        return HttpResponse.json({ id: 50, email: datos.email, rol: "event_owner" }, { status: 201 });
      }),
    );
    const { user } = renderEn("/admin/event-owners");
    await user.type(screen.getByLabelText("Email"), "org@x.com");
    await user.type(screen.getByLabelText("Contraseña inicial"), "organizador-2026");
    await user.click(screen.getByRole("button", { name: "Crear organizador" }));
    expect(await screen.findByText("Organizador org@x.com creado.")).toBeInTheDocument();
  });

  test("el menú de administración solo aparece para admin", async () => {
    server.use(http.get(`${API}/api/eventos`, () => HttpResponse.json([])));
    iniciarSesion("administrador");
    renderEn("/");
    expect(within(screen.getByRole("navigation")).getByRole("link", { name: "Administración" })).toBeInTheDocument();
  });

  test("un cliente que entra a /admin vuelve a la portada", async () => {
    server.use(http.get(`${API}/api/eventos`, () => HttpResponse.json([])));
    iniciarSesion("cliente");
    renderEn("/admin/usuarios");
    expect(await screen.findByRole("heading", { name: "Cartelera" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Administración" })).not.toBeInTheDocument();
  });
});
