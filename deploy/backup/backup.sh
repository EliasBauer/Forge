#!/bin/sh
set -eu

umask 077

BACKUP_ROOT=${BACKUP_ROOT:-/backups/local}
BACKUP_SHARE=${BACKUP_SHARE:-/backups/share}
PUSHGATEWAY_URL=${PUSHGATEWAY_URL:-}
POSTGRES_HOST=${POSTGRES_HOST:-postgres}
POSTGRES_PORT=${POSTGRES_PORT:-5432}
POSTGRES_PASSWORD_FILE=${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}
POSTGRES_READY_ATTEMPTS=${POSTGRES_READY_ATTEMPTS:-30}
POSTGRES_READY_DELAY_SECONDS=${POSTGRES_READY_DELAY_SECONDS:-2}
SOURCE_REVISION=${SOURCE_REVISION:-unknown}

started_at=$(date -u +%s)
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
staging_dir="${BACKUP_ROOT}/.${timestamp}.tmp"
final_dir="${BACKUP_ROOT}/${timestamp}"

cleanup_staging() {
    rm -rf "$staging_dir" || true
}

push_payload() {
    description=$1
    if [ -z "$PUSHGATEWAY_URL" ]; then
        cat >/dev/null
        return 0
    fi
    if ! curl --fail --silent --show-error \
        --connect-timeout 2 --max-time 5 --data-binary @- \
        "${PUSHGATEWAY_URL%/}/metrics/job/forge_backup"; then
        echo "backup metric push failed: $description" >&2
    fi
    return 0
}

push_metric() {
    metric=$1
    value=$2
    printf '%s %s\n' "$metric" "$value" | push_payload "$metric"
}

finalize_backup() {
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
    cleanup_staging
    {
        printf 'backup_last_attempt_timestamp_seconds %s\n' "$finished_at"
        printf 'backup_last_attempt_success %s\n' "$success"
        printf 'backup_last_duration_seconds %s\n' "$duration"
    } | push_payload "attempt completion"
    exit "$status"
}

trap finalize_backup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

apply_daily_retention() {
    find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d \
        -name '20??????T??????Z' -print |
        sort -r |
        awk 'NR > 30' |
        while IFS= read -r expired; do
            test "$expired" = "$final_dir" || rm -rf "$expired"
        done
}

apply_monthly_retention() {
    monthly_root="${BACKUP_ROOT}/monthly"
    month=$(date -u +%Y-%m)
    mkdir -p "$monthly_root"
    rm -rf "${monthly_root}/.${month}.tmp"
    cp -a "$final_dir" "${monthly_root}/.${month}.tmp"
    rm -rf "${monthly_root:?}/${month}"
    mv "${monthly_root}/.${month}.tmp" "${monthly_root}/${month}"
    find "$monthly_root" -mindepth 1 -maxdepth 1 -type d \
        -name '????-??' -print |
        sort -r |
        awk 'NR > 12' |
        while IFS= read -r expired; do
            rm -rf "$expired"
        done
}

wait_for_postgres() {
    attempt=1
    while [ "$attempt" -le "$POSTGRES_READY_ATTEMPTS" ]; do
        if pg_isready \
            --host="$POSTGRES_HOST" \
            --port="$POSTGRES_PORT" \
            --username="$POSTGRES_USER" \
            --dbname="$POSTGRES_DB" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$POSTGRES_READY_DELAY_SECONDS"
        attempt=$((attempt + 1))
    done

    echo "backup failed: postgres is not reachable at ${POSTGRES_HOST}:${POSTGRES_PORT}" >&2
    pg_isready \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" >&2 || true
    exit 1
}

test -r "$POSTGRES_PASSWORD_FILE"
export PGPASSWORD
PGPASSWORD=$(cat "$POSTGRES_PASSWORD_FILE")

mkdir -p "$BACKUP_ROOT" "$BACKUP_SHARE"
rm -rf "$staging_dir"
mkdir "$staging_dir"

wait_for_postgres

pg_dump \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --file="${staging_dir}/database.dump"

pg_restore --list "${staging_dir}/database.dump" >/dev/null

apply_retention() {
    apply_daily_retention
    apply_monthly_retention
}

{
    printf 'created_at=%s\n' "$timestamp"
    printf 'SOURCE_REVISION=%s\n' "$SOURCE_REVISION"
    printf 'postgres_database=%s\n' "$POSTGRES_DB"
} >"${staging_dir}/manifest.txt"

(
    cd "$staging_dir"
    sha256sum database.dump manifest.txt >SHA256SUMS
    sha256sum -c SHA256SUMS
)

mv "$staging_dir" "$final_dir"
backup_size=$(du -sk "$final_dir" | awk '{print $1 * 1024}')
push_metric backup_last_success_timestamp_seconds "$(date -u +%s)"
push_metric backup_size_bytes "$backup_size"

if ! rsync --archive --partial "$final_dir/" "${BACKUP_SHARE}/${timestamp}/"; then
    push_metric backup_transfer_last_failure_timestamp_seconds "$(date -u +%s)"
    exit 1
fi

push_metric backup_transfer_last_success_timestamp_seconds "$(date -u +%s)"
apply_retention
