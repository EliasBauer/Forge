#!/bin/sh
set -eu

# ----------------------------------------------------------------------------
# Deployment preflight validation script
#
# Purpose:
# - Validates critical runtime configuration before deployment starts.
# - Fails fast with actionable error messages for missing tools, invalid TLS
#   assets, missing directories, weak secrets, and unsafe compose exposure.
#
# What this script checks:
# 1) Required tooling (`docker`, `docker compose`, `flock`, `getent`, `stat`,
#    `openssl`), deployment group membership, and compose syntax validity.
# 2) TLS files exist/readable; the certificate is not expired and matches the key.
# 3) Required data/share directories exist, have the expected ownership and
#    modes for each container identity, and have enough free disk space.
# 4) Secret files in `${SECRETS_DIR}/*.txt` are group-private, readable,
#    non-empty, and not left at placeholder values.
# 5) Public domains for app/monitoring/admin are distinct host names.
# 6) Stateful services (`postgres`, `pgbouncer`, `redis`, `meilisearch`) do
#    not publish host ports in the rendered compose config.
#
# Important environment variables:
# - ENV_FILE (optional): Path to env file; default: <deploy>/.env
# - MIN_FREE_GB (optional): Minimum free space threshold; default: 5 GiB
# - TLS_CERT_FILE, TLS_KEY_FILE, DATA_ROOT, BACKUP_SHARE, SECRETS_DIR
# - APP_DOMAIN, MONITORING_DOMAIN, ADMIN_DOMAIN, DEPLOY_GROUP
# ----------------------------------------------------------------------------

DEPLOY_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
ENV_FILE=${ENV_FILE:-"$DEPLOY_DIR/.env"}
MIN_FREE_GB=${MIN_FREE_GB:-5}
APP_UID=${APP_UID:-1000}
APP_GID=${APP_GID:-1000}
NOBODY_UID=${NOBODY_UID:-65534}
NOBODY_GID=${NOBODY_GID:-65534}
GRAFANA_UID=${GRAFANA_UID:-472}
GRAFANA_GID=${GRAFANA_GID:-0}
LOKI_UID=${LOKI_UID:-10001}
LOKI_GID=${LOKI_GID:-10001}
PGADMIN_UID=${PGADMIN_UID:-5050}
PGADMIN_GID=${PGADMIN_GID:-5050}
ENV_FILE_IS_REAL=false
if [ -e "$ENV_FILE" ]; then
    test -r "$ENV_FILE" || {
        echo "preflight failed: DEPLOY_ENV_FILE is not readable: $ENV_FILE" >&2
        exit 1
    }
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
    ENV_FILE_IS_REAL=true
elif [ -r "$DEPLOY_DIR/.env.example" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$DEPLOY_DIR/.env.example"
    set +a
fi
ALERT_TEAMS_ENABLED=${ALERT_TEAMS_ENABLED:-false}
ALERT_SMTP_AUTH_ENABLED=${ALERT_SMTP_AUTH_ENABLED:-false}
# Secret files live in SECRETS_DIR (relative to deploy/ or absolute, e.g.
# /etc/forge/secrets); Compose reads the same variable from ENV_FILE.
SECRETS_DIR=${SECRETS_DIR:-./secrets}
case "$SECRETS_DIR" in
    /*) ;;
    *) SECRETS_DIR=$DEPLOY_DIR/$SECRETS_DIR ;;
esac
TEAMS_WORKFLOW_URL_FILE=$SECRETS_DIR/teams_workflow_url.txt
BEXIO_ACCESS_TOKEN_FILE=$SECRETS_DIR/bexio_access_token.txt
SMTP_PASSWORD_SECRET_FILE=$SECRETS_DIR/smtp_password.txt

# Print a standardized preflight error and abort.
fail() {
    echo "preflight failed: $*" >&2
    exit 1
}

warn() {
    echo "preflight warning: $*" >&2
}

# Ensure a required command is available in PATH.
require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

# shellcheck source=lib/compose.sh
. "$DEPLOY_DIR/scripts/lib/compose.sh"

# Ensure a configured file path is present and readable.
require_readable_file() {
    name=$1
    path=$2
    test -n "$path" || fail "$name is not configured"
    test -r "$path" || fail "$name is not readable: $path"
}

# Ensure a configured directory path is present and exists.
require_directory() {
    name=$1
    path=$2
    test -n "$path" || fail "$name is not configured"
    test -d "$path" || fail "$name does not exist: $path"
}

# Ensure a public domain is configured as a host name, not a URL or path.
require_domain() {
    name=$1
    value=$2
    test -n "$value" || fail "$name is not configured"
    case "$value" in
        *://*|*/*) fail "$name must be a host name, not a URL or path" ;;
    esac
}

# Ensure a required environment variable is configured with a real value.
require_env() {
    name=$1
    eval "value=\${$name:-}"
    test -n "$value" || fail "$name is not configured"
    test "$value" != "CHANGE_ME" || fail "$name still contains CHANGE_ME"
    case "$value" in
        *REPLACE_WITH*) fail "$name still contains placeholder: $value" ;;
    esac
}

# Ensure the filesystem containing `path` has at least MIN_FREE_GB available.
require_free_space() {
    name=$1
    path=$2
    free_kb=$(df -Pk "$path" | awk 'NR == 2 {print $4}')
    required_kb=$((MIN_FREE_GB * 1024 * 1024))
    test "$free_kb" -ge "$required_kb" || fail "$name has less than ${MIN_FREE_GB}GiB free"
}

# Ensure a host bind mount is privately writable by the requested container identity.
require_identity_writable_directory() {
    name=$1
    path=$2
    expected_uid=$3
    expected_gid=$4
    description=$5
    require_directory "$name" "$path"

    metadata=$(stat -c '%u %g %a' "$path" 2>/dev/null) || {
        fail "$name permissions cannot be inspected: $path"
    }
    set -- $metadata
    owner_uid=$1
    owner_gid=$2
    mode=$3

    owner_perm=$((mode / 100 % 10))
    group_perm=$((mode / 10 % 10))
    other_perm=$((mode % 10))

    if [ $((other_perm & 2)) -ne 0 ]; then
        fail "$name must not be world-writable: $path"
    fi
    if [ "$owner_uid" = "$expected_uid" ] && [ $((owner_perm & 2)) -ne 0 ]; then
        return 0
    fi
    if [ "$owner_gid" = "$expected_gid" ] && [ $((group_perm & 2)) -ne 0 ]; then
        return 0
    fi

    fail "$name is not writable by $description UID:GID ${expected_uid}:${expected_gid}: $path"
}

# Require a directory shared by deployment operators to have exactly the
# ownership and setgid mode expected by the operation-lock and runtime files.
require_shared_directory() {
    name=$1
    path=$2
    expected_mode=$3
    require_directory "$name" "$path"

    metadata=$(stat -c '%g %a' "$path" 2>/dev/null) || {
        fail "$name permissions cannot be inspected: $path"
    }
    set -- $metadata
    group_gid=$1
    mode=$2

    test "$group_gid" = "$DEPLOY_GROUP_GID" || {
        fail "$name must be owned by DEPLOY_GROUP $DEPLOY_GROUP: $path"
    }
    test "$mode" = "$expected_mode" || {
        fail "$name must have mode $expected_mode: $path"
    }
    test -w "$path" || {
        fail "$name is not writable by the host operator: $path"
    }
}

# Require shared configuration to be group-readable but inaccessible to users
# outside the deployment group. Never include file contents in diagnostics.
require_group_readable_private_file() {
    name=$1
    path=$2
    require_readable_file "$name" "$path"

    metadata=$(stat -c '%g %a' "$path" 2>/dev/null) || {
        fail "$name permissions cannot be inspected: $path"
    }
    set -- $metadata
    group_gid=$1
    mode=$2
    group_perm=$((mode / 10 % 10))
    other_perm=$((mode % 10))

    test "$group_gid" = "$DEPLOY_GROUP_GID" || {
        fail "$name must be owned by DEPLOY_GROUP $DEPLOY_GROUP: $path"
    }
    test "$other_perm" -eq 0 || {
        fail "$name must not grant any world permissions: $path"
    }
    test $((group_perm & 4)) -ne 0 || {
        fail "$name must be group-readable: $path"
    }
}

# Preserve the app-owned bind mount contract with the shared identity check.
require_container_writable_directory() {
    require_identity_writable_directory "$1" "$2" "$APP_UID" "$APP_GID" "app container"
}

# Validate secret file content quality (readable, non-empty, not placeholder).
check_secret() {
    file=$1
    test -r "$file" || fail "secret file is not readable: $file"
    value=$(sed -n '1p' "$file")
    test -n "$value" || fail "secret file is empty: $file"
    test "$value" != "CHANGE_ME" || fail "secret file contains a placeholder: $file"
    test "$value" != "CHANGE_ME_" || fail "secret file contains a placeholder: $file"
}

require_command docker
require_command flock
require_command getent
require_command stat
require_command openssl

require_env DEPLOY_GROUP
DEPLOY_GROUP_RECORD=$(getent group "$DEPLOY_GROUP") || {
    fail "DEPLOY_GROUP does not exist: $DEPLOY_GROUP"
}
DEPLOY_GROUP_GID=$(printf '%s\n' "$DEPLOY_GROUP_RECORD" | awk -F: '{print $3}')
case "$DEPLOY_GROUP_GID" in
    ""|*[!0-9]*) fail "DEPLOY_GROUP has no numeric GID: $DEPLOY_GROUP" ;;
esac
case " $(id -Gn) " in
    *" $DEPLOY_GROUP "*) ;;
    *) fail "current user is not a member of DEPLOY_GROUP $DEPLOY_GROUP; start a new login session after changing group membership" ;;
esac

if [ "$ENV_FILE_IS_REAL" = true ]; then
    require_group_readable_private_file DEPLOY_ENV_FILE "$ENV_FILE"
fi

docker info >/dev/null 2>&1 || {
    fail "current user cannot access the Docker daemon; add the operator to the Docker access group and start a new login session"
}

# Validate public host names before rendering compose values that derive URLs.
require_domain APP_DOMAIN "${APP_DOMAIN:-}"
require_domain MONITORING_DOMAIN "${MONITORING_DOMAIN:-}"
require_domain ADMIN_DOMAIN "${ADMIN_DOMAIN:-}"

# pgAdmin validiert die Login-Adresse strikt und verweigert Special-Use-Domains.
require_env PGADMIN_DEFAULT_EMAIL
case "$PGADMIN_DEFAULT_EMAIL" in
    *@*.local|*@*.localhost|*@*.test|*@*.example|*@*.invalid|*@localhost|*@example.com|*@example.net|*@example.org)
        fail "PGADMIN_DEFAULT_EMAIL must not use a special-use domain (pgAdmin rejects it)" ;;
    *@*.*) ;;
    *) fail "PGADMIN_DEFAULT_EMAIL must be a full e-mail address" ;;
esac

# Validate rendered compose configuration for basic correctness.
cd "$DEPLOY_DIR"
compose config --quiet

# Validate TLS assets and enforce certificate-key pairing (RSA and EC keys).
require_readable_file TLS_CERT_FILE "${TLS_CERT_FILE:-}"
require_readable_file TLS_KEY_FILE "${TLS_KEY_FILE:-}"
openssl x509 -in "$TLS_CERT_FILE" -noout -checkend 0 >/dev/null
cert_public_key=$(openssl x509 -pubkey -noout -in "$TLS_CERT_FILE" | openssl md5)
key_public_key=$(openssl pkey -pubout -in "$TLS_KEY_FILE" 2>/dev/null | openssl md5)
test "$cert_public_key" = "$key_public_key" || fail "TLS certificate and key do not match"

# Validate required storage locations and minimum free space.
require_directory DATA_ROOT "${DATA_ROOT:-}"
require_directory BACKUP_SHARE "${BACKUP_SHARE:-}"
require_shared_directory RUN_DIRECTORY "$DATA_ROOT/run" 2770
require_shared_directory RUNTIME_DIRECTORY "$DATA_ROOT/runtime" 2770
require_shared_directory NODE_EXPORTER_TEXTFILE "$DATA_ROOT/runtime/node-exporter" 2775
require_free_space DATA_ROOT "$DATA_ROOT"
require_free_space BACKUP_SHARE "$BACKUP_SHARE"
require_container_writable_directory DATA_ROOT_STATIC "$DATA_ROOT/static"
require_container_writable_directory DATA_ROOT_BACKUPS "$DATA_ROOT/backups"
require_container_writable_directory DATA_ROOT_CELERYBEAT "$DATA_ROOT/celerybeat"
require_container_writable_directory DATA_ROOT_RESTORE_FILES "$DATA_ROOT/restore-verification/files"
require_container_writable_directory BACKUP_SHARE "$BACKUP_SHARE"
require_identity_writable_directory ALERTMANAGER_DATA "$DATA_ROOT/alertmanager" "$NOBODY_UID" "$NOBODY_GID" "Alertmanager container"
require_identity_writable_directory PROMETHEUS_DATA "$DATA_ROOT/prometheus" "$NOBODY_UID" "$NOBODY_GID" "Prometheus container"
require_identity_writable_directory PUSHGATEWAY_DATA "$DATA_ROOT/pushgateway" "$NOBODY_UID" "$NOBODY_GID" "Pushgateway container"
require_identity_writable_directory GRAFANA_DATA "$DATA_ROOT/grafana" "$GRAFANA_UID" "$GRAFANA_GID" "Grafana container"
require_identity_writable_directory LOKI_DATA "$DATA_ROOT/loki" "$LOKI_UID" "$LOKI_GID" "Loki container"
require_identity_writable_directory PGADMIN_DATA "$DATA_ROOT/pgadmin" "$PGADMIN_UID" "$PGADMIN_GID" "pgAdmin container"

# Validate secrets. Optional secrets have explicit rules; every other
# non-example file in SECRETS_DIR must be a real, group-private value.
require_directory SECRETS_DIR "$SECRETS_DIR"
if [ "$ALERT_SMTP_AUTH_ENABLED" = true ]; then
    SMTP_PASSWORD_FILE=${ALERT_SMTP_PASSWORD_FILE:-$SMTP_PASSWORD_SECRET_FILE}
    test "$SMTP_PASSWORD_FILE" != /dev/null || fail "ALERT_SMTP_PASSWORD_FILE must point to a secret file when SMTP authentication is enabled"
    case "$SMTP_PASSWORD_FILE" in
        /*) ;;
        *) SMTP_PASSWORD_FILE=$DEPLOY_DIR/$SMTP_PASSWORD_FILE ;;
    esac
    require_group_readable_private_file "SMTP password secret" "$SMTP_PASSWORD_FILE"
    check_secret "$SMTP_PASSWORD_FILE"
fi
require_group_readable_private_file "Teams Workflow secret" "$TEAMS_WORKFLOW_URL_FILE"
ALERT_TEAMS_ENABLED=$ALERT_TEAMS_ENABLED \
    TEAMS_WORKFLOW_URL_FILE=$TEAMS_WORKFLOW_URL_FILE \
    sh "$DEPLOY_DIR/scripts/validate-teams-workflow.sh"
require_group_readable_private_file "Bexio access token secret" "$BEXIO_ACCESS_TOKEN_FILE"
if [ -z "$(sed -n '1p' "$BEXIO_ACCESS_TOKEN_FILE")" ]; then
    warn "bexio_access_token.txt is empty; the backend runs in Bexio dev mode with fixture data"
fi
for file in "$SECRETS_DIR"/*.txt; do
    case "$file" in
        "$TEAMS_WORKFLOW_URL_FILE"|"$BEXIO_ACCESS_TOKEN_FILE"|"$SMTP_PASSWORD_SECRET_FILE"|*.example) continue ;;
    esac
    require_group_readable_private_file "secret file" "$file"
    check_secret "$file"
done

# Enforce domain separation between app, monitoring, and admin endpoints.
test "${APP_DOMAIN:-}" != "${MONITORING_DOMAIN:-}" || fail "APP_DOMAIN and MONITORING_DOMAIN must differ"
test "${APP_DOMAIN:-}" != "${ADMIN_DOMAIN:-}" || fail "APP_DOMAIN and ADMIN_DOMAIN must differ"
test "${MONITORING_DOMAIN:-}" != "${ADMIN_DOMAIN:-}" || fail "MONITORING_DOMAIN and ADMIN_DOMAIN must differ"

# Ensure stateful services are not directly exposed on host ports.
published_stateful=$(compose config | awk '
    /^  (postgres|pgbouncer|redis|meilisearch|restore-postgres):$/ {service=$1; sub(":", "", service)}
    /^  [a-zA-Z0-9_-]+:$/ && !/^  (postgres|pgbouncer|redis|meilisearch|restore-postgres):$/ {service=""}
    service != "" && /published:/ {print service}
')
test -z "$published_stateful" || fail "stateful services publish host ports: $published_stateful"

echo "preflight ok"
