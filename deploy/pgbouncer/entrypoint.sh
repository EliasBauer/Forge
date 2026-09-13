#!/bin/sh
set -eu

password_file=/run/secrets/postgres_password
test -r "$password_file" || {
  echo "PostgreSQL password secret is not readable" >&2
  exit 1
}

postgres_user=${POSTGRES_USER:-forge}
postgres_db=${POSTGRES_DB:-forge}
max_client_conn=${PGBOUNCER_MAX_CLIENT_CONN:-200}
default_pool_size=${PGBOUNCER_DEFAULT_POOL_SIZE:-20}
reserve_pool_size=${PGBOUNCER_RESERVE_POOL_SIZE:-5}

escaped_user=$(printf '%s' "$postgres_user" | sed 's/\\/\\\\/g; s/"/\\"/g')
escaped_password=$(
  sed 's/\\/\\\\/g; s/"/\\"/g' "$password_file" | tr -d '\r\n'
)
printf '"%s" "%s"\n' "$escaped_user" "$escaped_password" > /tmp/userlist.txt
chmod 0600 /tmp/userlist.txt

cat > /tmp/pgbouncer.ini <<EOT
[databases]
${postgres_db} = host=postgres port=5432 dbname=${postgres_db}

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 5432
auth_type = scram-sha-256
auth_file = /tmp/userlist.txt
stats_users = ${escaped_user}
pool_mode = transaction
max_client_conn = ${max_client_conn}
default_pool_size = ${default_pool_size}
reserve_pool_size = ${reserve_pool_size}
server_reset_query = DISCARD ALL
ignore_startup_parameters = extra_float_digits
EOT

exec pgbouncer /tmp/pgbouncer.ini
