#!/bin/sh
set -eu

umask 077

PUSHGATEWAY_URL=${PUSHGATEWAY_URL:-}
started_at=$(date -u +%s)

push_payload() {
    description=$1
    if [ -z "$PUSHGATEWAY_URL" ]; then
        cat >/dev/null
        return 0
    fi
    if ! curl --fail --silent --show-error \
        --connect-timeout 2 --max-time 5 --data-binary @- \
        "${PUSHGATEWAY_URL%/}/metrics/job/forge_restore_verification"; then
        echo "restore verification metric push failed: $description" >&2
    fi
    return 0
}

push_metric() {
    metric=$1
    value=$2
    printf '%s %s\n' "$metric" "$value" | push_payload "$metric"
}

finalize_restore_verification() {
    status=$?
    trap - EXIT HUP INT TERM
    finished_at=$(date -u +%s)
    duration=$((finished_at - started_at))
    if [ "$duration" -lt 0 ]; then
        duration=0
    fi
    success=0
    if [ "$status" -eq 0 ]; then
        success=1
    fi
    {
        printf 'restore_verification_last_attempt_timestamp_seconds %s\n' "$finished_at"
        printf 'restore_verification_last_attempt_success %s\n' "$success"
        printf 'restore_verification_last_duration_seconds %s\n' "$duration"
    } | push_payload "attempt completion"
    exit "$status"
}

trap finalize_restore_verification EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

backup_dir=${1:-${RESTORE_BACKUP:-}}
test -n "$backup_dir"
test -d "$backup_dir"
test -d /restore/postgres

(
    cd "$backup_dir"
    sha256sum -c SHA256SUMS
)

test -r "${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}"
export PGPASSWORD
PGPASSWORD=$(cat "${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}")

psql \
    --host="${POSTGRES_HOST:-restore-postgres}" \
    --port="${POSTGRES_PORT:-5432}" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --set=ON_ERROR_STOP=1 \
    --command="DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

pg_restore \
    --host="${POSTGRES_HOST:-restore-postgres}" \
    --port="${POSTGRES_PORT:-5432}" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --no-owner \
    --no-privileges \
    "${backup_dir}/database.dump"

python manage.py check
python manage.py showmigrations --plan
push_metric restore_verification_last_success_timestamp_seconds "$(date -u +%s)"
