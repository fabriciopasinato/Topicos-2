// Requirement "Sesión del usuario en el frontend": renovación del token en las
// rutas protegidas de auth y rutas públicas de auth llamadas sin token.
import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";
import { api, esLecturaPublica, guardarTokens, RUTAS_PUBLICAS_AUTH, tokensActuales } from "./api/client.js";
import { API, server } from "./test/server.js";
import { DISPONIBILIDAD, EVENTO, iniciarSesion, renderEn, tokenFalso } from "./test/utilidades.jsx";

const PERFIL = {
  id: 20, email: "ana@example.com", rol: "cliente", estado: "activa", nombre: "Ana", apellido: "Pérez",
  dni: "30123456", fecha_nacimiento: "1990-05-17", telefono: "2215551234", calle: "Calle 7", numero: "1234",
  piso_depto: null, localidad: "La Plata", provincia: "Buenos Aires", codigo_postal: "1900",
  created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-05T10:00:00Z", last_login_at: "2026-11-09T10:00:00Z",
};

/** El access actual es "vencido": la ruta responde 401 hasta que llegue el renovado. */
function conTokenVencido(rol, metodo, ruta, respuesta) {
  const renovado = tokenFalso(20, rol) + "-renovado";
  const llamadas = { ruta: 0, refresh: 0 };
  server.use(
    http[metodo](`${API}${ruta}`, ({ request }) => {
      llamadas.ruta += 1;
      return request.headers.get("Authorization") === `Bearer ${renovado}`
        ? HttpResponse.json(respuesta)
        : HttpResponse.json({ detail: "token invalido o expirado" }, { status: 401 });
    }),
    http.post(`${API}/api/auth/refresh`, () => {
      llamadas.refresh += 1;
      return HttpResponse.json({ access_token: renovado, refresh_token: "R2", expires_in: 7200 });
    }),
  );
  return llamadas;
}

describe("rutas públicas de auth (6.1)", () => {
  test("son exactamente las 7 del gateway", () => {
    expect([...RUTAS_PUBLICAS_AUTH].sort()).toEqual([
      "/api/auth/login",
      "/api/auth/olvide-contrasenia",
      "/api/auth/reenviar-verificacion",
      "/api/auth/refresh",
      "/api/auth/registro",
      "/api/auth/restablecer-contrasenia",
      "/api/auth/verificar-email",
    ]);
  });

  test("se llaman sin Authorization aunque haya sesión; las protegidas lo llevan", async () => {
    guardarTokens({ access_token: "A1", refresh_token: "R1" });
    const headers = {};
    server.use(
      http.post(`${API}/api/auth/olvide-contrasenia`, ({ request }) => {
        headers.publica = request.headers.get("Authorization");
        return HttpResponse.json({ detail: "ok" }, { status: 202 });
      }),
      http.get(`${API}/api/auth/perfil`, ({ request }) => {
        headers.protegida = request.headers.get("Authorization");
        return HttpResponse.json(PERFIL);
      }),
    );
    await api("/api/auth/olvide-contrasenia", { method: "POST", body: { email: "a@b.c" } });
    await api("/api/auth/perfil");
    expect(headers).toEqual({ publica: null, protegida: "Bearer A1" });
  });
});

describe("renovación en rutas protegidas de auth (6.2)", () => {
  test("perfil con el token vencido: renueva, reintenta y lo muestra", async () => {
    iniciarSesion();
    const llamadas = conTokenVencido("cliente", "get", "/api/auth/perfil", PERFIL);
    renderEn("/perfil");
    expect(await screen.findByText("30123456")).toBeInTheDocument();
    expect(llamadas).toEqual({ ruta: 2, refresh: 1 });
    expect(tokensActuales().refresh).toBe("R2");
    expect(screen.getByRole("link", { name: "Mi perfil" })).toBeInTheDocument();
  });

  test("listado de cuentas del admin con el token vencido: renueva y lo muestra", async () => {
    iniciarSesion("administrador");
    const llamadas = conTokenVencido("administrador", "get", "/api/auth/admin/usuarios", {
      items: [], total: 0, pagina: 1, tamanio: 20,
    });
    renderEn("/admin/usuarios");
    expect(await screen.findByText("0 cuenta(s)")).toBeInTheDocument();
    expect(llamadas).toEqual({ ruta: 2, refresh: 1 });
  });

  test("si el refresh se rechaza en el perfil, cierra la sesión con aviso", async () => {
    iniciarSesion();
    server.use(
      http.get(`${API}/api/auth/perfil`, () => HttpResponse.json({ detail: "x" }, { status: 401 })),
      http.post(`${API}/api/auth/refresh`, () => HttpResponse.json({ detail: "x" }, { status: 401 })),
    );
    renderEn("/perfil");
    expect(await screen.findByRole("heading", { name: "Ingresar" })).toBeInTheDocument();
    expect(screen.getByText(/sesión/i)).toBeInTheDocument();
    expect(tokensActuales()).toBeNull();
  });
});

describe("restablecimiento con una sesión revocada en el navegador (6.3)", () => {
  test("se envía sin token, funciona y no intenta renovar", async () => {
    guardarTokens({ access_token: "revocado", refresh_token: "R-revocado" });
    let refresh = 0;
    server.use(
      // Así se comporta el gateway con un token revocado, aunque la ruta sea pública.
      http.post(`${API}/api/auth/restablecer-contrasenia`, ({ request }) =>
        request.headers.get("Authorization")
          ? HttpResponse.json({ detail: "la sesion fue revocada" }, { status: 401 })
          : HttpResponse.json({ detail: "ok" }),
      ),
      http.post(`${API}/api/auth/refresh`, () => {
        refresh += 1;
        return HttpResponse.json({ detail: "x" }, { status: 401 });
      }),
    );
    const { user } = renderEn("/restablecer?token=xyz");
    await user.type(screen.getByLabelText("Contraseña nueva"), "jirafa-violeta-77");
    await user.type(screen.getByLabelText("Repetir contraseña"), "jirafa-violeta-77");
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Contraseña actualizada");
    expect(refresh).toBe(0);
  });

  test("al restablecer se descarta la sesión guardada (6.5)", async () => {
    iniciarSesion();
    server.use(
      http.post(`${API}/api/auth/restablecer-contrasenia`, () => HttpResponse.json({ detail: "ok" })),
    );
    const { user } = renderEn("/restablecer?token=xyz");
    expect(screen.getByRole("link", { name: "Mi perfil" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Contraseña nueva"), "jirafa-violeta-77");
    await user.type(screen.getByLabelText("Repetir contraseña"), "jirafa-violeta-77");
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Contraseña actualizada");
    expect(tokensActuales()).toBeNull();
    expect(screen.queryByRole("link", { name: "Mi perfil" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ingresar" })).toBeInTheDocument();
  });
});

describe("lecturas públicas con la sesión revocada", () => {
  /** Como el gateway: con un token revocado responde 401 aunque la ruta sea pública. */
  function publica(ruta, datos) {
    return http.get(`${API}${ruta}`, ({ request }) =>
      request.headers.get("Authorization")
        ? HttpResponse.json({ detail: "la sesion fue revocada" }, { status: 401 })
        : HttpResponse.json(datos));
  }
  const refreshRevocado = http.post(`${API}/api/auth/refresh`, () =>
    HttpResponse.json({ detail: "x" }, { status: 401 }));

  test("la lista de lecturas públicas", () => {
    expect(esLecturaPublica("GET", "/api/eventos?tipo=recital")).toBe(true);
    expect(esLecturaPublica("GET", "/api/eventos/tipos")).toBe(true);
    expect(esLecturaPublica("GET", "/api/eventos/recintos")).toBe(true);
    expect(esLecturaPublica("GET", "/api/eventos/7")).toBe(true);
    expect(esLecturaPublica("GET", "/api/ventas/eventos/7/disponibilidad")).toBe(true);
    expect(esLecturaPublica("GET", "/api/eventos/mios")).toBe(false);
    expect(esLecturaPublica("POST", "/api/eventos")).toBe(false);
    expect(esLecturaPublica("GET", "/api/ventas/compras")).toBe(false);
  });

  test("la cartelera se muestra, la sesión se descarta y el encabezado ofrece ingresar", async () => {
    iniciarSesion();
    server.use(publica("/api/eventos", [{ ...EVENTO, id: 1 }]), refreshRevocado);
    renderEn("/");
    expect(await screen.findByText("Recital de prueba")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cartelera" })).toBeInTheDocument();
    expect(tokensActuales()).toBeNull();
    expect(await screen.findByRole("link", { name: "Ingresar" })).toBeInTheDocument();
  });

  test("el detalle de un evento y su disponibilidad se muestran", async () => {
    iniciarSesion();
    server.use(
      publica("/api/eventos/1", EVENTO),
      publica("/api/ventas/eventos/1/disponibilidad", DISPONIBILIDAD),
      refreshRevocado,
    );
    renderEn("/eventos/1");
    expect(await screen.findByRole("heading", { name: "Recital de prueba" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ingresar" })).not.toBeInTheDocument();
  });

  test("mis eventos lleva al login con el aviso de sesión cerrada", async () => {
    iniciarSesion("event_owner");
    server.use(
      http.get(`${API}/api/eventos/mios`, () => HttpResponse.json({ detail: "x" }, { status: 401 })),
      refreshRevocado,
    );
    renderEn("/owner");
    expect(await screen.findByRole("heading", { name: "Ingresar" })).toBeInTheDocument();
    expect(screen.getByText("Tu sesión se cerró. Volvé a ingresar.")).toBeInTheDocument();
  });
});

describe("401 en una ruta pública de auth (6.4)", () => {
  test("login con credenciales inválidas no intenta renovar ni borra la sesión guardada", async () => {
    guardarTokens({ access_token: "A1", refresh_token: "R1" });
    let refresh = 0;
    server.use(
      http.post(`${API}/api/auth/login`, () =>
        HttpResponse.json({ detail: "Email o contraseña incorrectos.", codigo: "credenciales_invalidas" },
          { status: 401 })),
      http.post(`${API}/api/auth/refresh`, () => {
        refresh += 1;
        return HttpResponse.json({ detail: "x" }, { status: 401 });
      }),
    );
    const error = await api("/api/auth/login", { method: "POST", body: {} }).catch((e) => e);
    expect(error.status).toBe(401);
    expect(refresh).toBe(0);
    expect(tokensActuales()).toEqual({ access: "A1", refresh: "R1" });
  });
});
