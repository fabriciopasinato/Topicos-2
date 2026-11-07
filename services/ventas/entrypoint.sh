#!/bin/sh
# Aplica las migraciones pendientes (idempotente) y despues levanta la API.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8003}"
