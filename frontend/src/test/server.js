import { setupServer } from "msw/node";

export const API = "http://localhost:8000";

// Cada test registra sus propios handlers con server.use(...)
export const server = setupServer();
