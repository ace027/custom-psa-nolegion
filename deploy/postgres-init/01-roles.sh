#!/bin/sh
# Runs once, on first database initialization. POSTGRES_USER (the owner) runs migrations;
# psa_app is the runtime role: not owner, no superuser, no BYPASSRLS, so row-level security applies.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE psa_app LOGIN PASSWORD '${APP_DB_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO psa_app;
SQL
