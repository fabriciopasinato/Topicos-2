#!/bin/bash
# Inicializacion de PostgreSQL: corre SOLO cuando el volumen de datos esta vacio
# (comportamiento estandar de /docker-entrypoint-initdb.d).
#
# Crea un usuario y una base por servicio, y deja que cada usuario solo pueda
# conectarse a su propia base. NO crea tablas: el esquema es responsabilidad
# de las migraciones Alembic de cada servicio.
#
# Variables requeridas: POSTGRES_USER, AUTH_DB_PASSWORD, EVENTOS_DB_PASSWORD,
# VENTAS_DB_PASSWORD, GATEWAY_DB_PASSWORD.
# Opcional: DB_SUFFIX (por ejemplo "_test" para la base de tests).
set -euo pipefail

SUFFIX="${DB_SUFFIX:-}"

psql_super() {
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" "$@"
}

# Nadie que no sea superusuario puede conectarse a las bases de mantenimiento.
psql_super --dbname postgres -c "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;"
psql_super --dbname postgres -c "REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;"

crear_base() {
  local usuario="$1" password="$2" base="$3${SUFFIX}"

  echo "init: creando usuario '${usuario}' y base '${base}'"
  psql_super --dbname postgres -v usuario="$usuario" -v password="$password" -v base="$base" <<'EOSQL'
CREATE USER :"usuario" WITH PASSWORD :'password';
CREATE DATABASE :"base" OWNER :"usuario";
REVOKE CONNECT ON DATABASE :"base" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"base" TO :"usuario";
EOSQL

  # El schema public queda solo para el duenio de la base.
  psql_super --dbname "$base" -v usuario="$usuario" <<'EOSQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO :"usuario";
EOSQL
}

crear_base auth    "$AUTH_DB_PASSWORD"    auth_db
crear_base eventos "$EVENTOS_DB_PASSWORD" eventos_db
crear_base ventas  "$VENTAS_DB_PASSWORD"  ventas_db
crear_base gateway "$GATEWAY_DB_PASSWORD" gateway_db

echo "init: listo"
