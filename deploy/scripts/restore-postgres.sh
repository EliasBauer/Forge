#!/bin/sh
set -eu

# Restore only PostgreSQL from a Forge backup directory.
#
# Usage:
#   CONFIRM_RESTORE_POSTGRES=true ./scripts/restore-postgres.sh /path/to/backup
#
# The backup directory must be below either ${DATA_ROOT}/backups or
# ${BACKUP_SHARE}, because the restore runs inside the existing backup service
# with those host paths mounted read-only/read-write by Compose.

DEPLOY_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
ENV_FILE=${ENV_FILE:-"$DEPLOY_DIR/.env"}

if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

usage() {
    cat >&2 <<EOF
Usage: CONFIRM_RESTORE_POSTGRES=true $0 [BACKUP_DIR]

BACKUP_DIR defaults to RESTORE_BACKUP when omitted.
This drops and recreates the public schema in the configured PostgreSQL DB.
Maintenance mode remains enabled after the restore.
EOF
}

fail() {
    echo "postgres restore failed: $*" >&2
    exit 1
}

# shellcheck source=lib/compose.sh
. "$DEPLOY_DIR/scripts/lib/compose.sh"

real_dir() {
    cd "$1" && pwd -P
}

enable_maintenance() {
    MAINTENANCE_TOKEN=$(SOURCE_REVISION="$SOURCE_REVISION" "$MAINTENANCE_HELPER" start restore "${RESTORE_MAINTENANCE_TIMEOUT_SECONDS:-7200}")
    MAINTENANCE_FINISH_COMMAND=$(ENV_FILE="$ENV_FILE" "$MAINTENANCE_HELPER" finish-command restore "$MAINTENANCE_TOKEN")
    printf 'manual finish command: %s\n' "$MAINTENANCE_FINISH_COMMAND" >&2
}

cleanup() {
    status=$?
    if [ "$OPERATION_LOCK_ACQUIRED" = true ]; then
        release_operation_lock
    fi
    if [ "$status" -ne 0 ]; then
        echo "postgres restore failed; maintenance mode remains enabled" >&2
    else
        echo "postgres restore completed; maintenance mode remains enabled" >&2
    fi
    if [ -n "$MAINTENANCE_FINISH_COMMAND" ]; then
        printf 'after verification, run: %s\n' "$MAINTENANCE_FINISH_COMMAND" >&2
    fi
    exit "$status"
}

container_backup_dir() {
    backup_real=$1
    local_root=$2
    share_root=$3

    case "$backup_real" in
        "$local_root")
            printf '%s\n' "/backups/local"
            ;;
        "$local_root"/*)
            printf '%s\n' "/backups/local/${backup_real#$local_root/}"
            ;;
        "$share_root")
            printf '%s\n' "/backups/share"
            ;;
        "$share_root"/*)
            printf '%s\n' "/backups/share/${backup_real#$share_root/}"
            ;;
        *)
            fail "BACKUP_DIR must be below $local_root or $share_root: $backup_real"
            ;;
    esac
}

ensure_database_ready() {
    cd "$DEPLOY_DIR"
    compose --env-file "$ENV_FILE" up -d postgres

    attempts=${POSTGRES_READY_ATTEMPTS:-30}
    delay_seconds=${POSTGRES_READY_DELAY_SECONDS:-2}
    attempt=1
    while [ "$attempt" -le "$attempts" ]; do
        if compose --env-file "$ENV_FILE" exec -T postgres pg_isready \
            -U "$POSTGRES_USER" \
            -d "$POSTGRES_DB" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$delay_seconds"
        attempt=$((attempt + 1))
    done

    compose --env-file "$ENV_FILE" ps postgres >&2 || true
    fail "postgres did not become ready after ${attempts} attempts"
}

run_restore() {
    cd "$DEPLOY_DIR"
    compose \
        --env-file "$ENV_FILE" \
        --profile backup \
        run --rm --no-deps \
        --entrypoint /bin/sh backup -ec '
backup_dir=$1
cd "$backup_dir"
sha256sum -c SHA256SUMS
test -r database.dump
test -r "$POSTGRES_PASSWORD_FILE"
export PGPASSWORD
PGPASSWORD=$(cat "$POSTGRES_PASSWORD_FILE")
psql \
    --host="$POSTGRES_HOST" \
    --port="${POSTGRES_PORT:-5432}" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --set=ON_ERROR_STOP=1 \
    --command="DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
pg_restore \
    --host="$POSTGRES_HOST" \
    --port="${POSTGRES_PORT:-5432}" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --no-owner \
    --no-privileges \
    "$backup_dir/database.dump"
' sh "$CONTAINER_BACKUP_DIR"
}

case "${1:-}" in
    -h | --help | help)
        usage
        exit 0
        ;;
esac

test -z "${2:-}" || {
    usage
    exit 2
}

DATA_ROOT=${DATA_ROOT:?DATA_ROOT is required}
BACKUP_SHARE=${BACKUP_SHARE:?BACKUP_SHARE is required}
POSTGRES_DB=${POSTGRES_DB:?POSTGRES_DB is required}
POSTGRES_USER=${POSTGRES_USER:?POSTGRES_USER is required}
BACKUP_DIR=${1:-${RESTORE_BACKUP:-}}
MAINTENANCE_FLAG_FILE=${MAINTENANCE_FLAG_FILE:-"$DATA_ROOT/runtime/maintenance"}
MAINTENANCE_HELPER="$DEPLOY_DIR/scripts/maintenance.sh"
SOURCE_REVISION=${SOURCE_REVISION:-unknown}
DEPLOY_GROUP=${DEPLOY_GROUP:-}
OPERATION_LOCK_HELPER="$DEPLOY_DIR/scripts/lib/operation-lock.sh"
MAINTENANCE_TOKEN=
MAINTENANCE_FINISH_COMMAND=

# shellcheck disable=SC1090
. "$OPERATION_LOCK_HELPER"

test "${CONFIRM_RESTORE_POSTGRES:-false}" = "true" ||
    fail "restore requires CONFIRM_RESTORE_POSTGRES=true"
test -n "$BACKUP_DIR" || {
    usage
    fail "BACKUP_DIR or RESTORE_BACKUP is required"
}
test -d "$BACKUP_DIR" || fail "BACKUP_DIR does not exist: $BACKUP_DIR"
test -r "$BACKUP_DIR/SHA256SUMS" || fail "SHA256SUMS is not readable: $BACKUP_DIR/SHA256SUMS"
test -r "$BACKUP_DIR/database.dump" || fail "database.dump is not readable: $BACKUP_DIR/database.dump"
test -d "$DATA_ROOT/backups" || fail "DATA_ROOT backups directory does not exist: $DATA_ROOT/backups"
test -d "$BACKUP_SHARE" || fail "BACKUP_SHARE does not exist: $BACKUP_SHARE"
SECRETS_DIR=${SECRETS_DIR:-./secrets}
case "$SECRETS_DIR" in
    /*) ;;
    *) SECRETS_DIR=$DEPLOY_DIR/$SECRETS_DIR ;;
esac
test -r "$SECRETS_DIR/postgres_password.txt" ||
    fail "PostgreSQL password secret is not readable: $SECRETS_DIR/postgres_password.txt"

BACKUP_REAL=$(real_dir "$BACKUP_DIR")
LOCAL_BACKUP_ROOT=$(real_dir "$DATA_ROOT/backups")
SHARE_BACKUP_ROOT=$(real_dir "$BACKUP_SHARE")
CONTAINER_BACKUP_DIR=$(container_backup_dir "$BACKUP_REAL" "$LOCAL_BACKUP_ROOT" "$SHARE_BACKUP_ROOT")

trap cleanup EXIT INT TERM

acquire_operation_lock restore
ensure_database_ready
enable_maintenance
run_restore
