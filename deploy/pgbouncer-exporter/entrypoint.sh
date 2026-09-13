#!/bin/sh
set -eu

password_file=${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}
test -r "$password_file"
export PGPASSWORD
PGPASSWORD=$(tr -d '\r\n' <"$password_file")
export PGBOUNCER_EXPORTER_CONNECTION_STRING
PGBOUNCER_EXPORTER_CONNECTION_STRING="host=${PGBOUNCER_HOST:-pgbouncer} port=${PGBOUNCER_PORT:-5432} user=${POSTGRES_USER} dbname=pgbouncer sslmode=disable"
exec /bin/pgbouncer_exporter
