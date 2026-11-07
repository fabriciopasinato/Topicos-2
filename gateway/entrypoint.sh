#!/bin/sh
# Aplica las migraciones pendientes (idempotente) y despues levanta el gateway.
set -e
alembic upgrade head
exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}"
