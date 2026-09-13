#!/bin/sh
set -eu

# ----------------------------------------------------------------------------
# Deployment script for the production setup (Docker Compose)
#
# Purpose:
# - Runs a full deployment flow (build, backup, migrations,
#   restart/scaling, health checks).
# - Serializes mutating operational workflows with the shared operation lock.
# - Enables a maintenance flag during deployment.
#
# Flow (in order):
# 1) Acquire lock
# 2) Validate configuration
# 3) Build images
# 4) Start and verify the database dependency
# 5) Enable maintenance mode
# 6) Run backup
# 7) Run migrations
# 8) Rebuild every configured search index
# 9) Start/scale services
# 10) Verify health
# 11) Disable maintenance mode
# 12) Reset application cache
#
# Important environment variables:
# - DATA_ROOT (required): Base directory for runtime/lock files.
# - ENV_FILE (optional): Path to the .env file, default: <deploy>/.env
# - SKIP_BACKUP (optional): Set to true only when retrying after a build-time
#   or pre-migration failure where no database changes were applied.
# - MAINTENANCE_FLAG_FILE (optional): Path to the maintenance file,
#   default: $DATA_ROOT/runtime/maintenance
# - WEB_REPLICAS, CELERY_REPLICAS (optional): scaling for compose up,
#   defaults are 2 web replicas and 1 worker.
# - HEALTHCHECK_ATTEMPTS, HEALTHCHECK_DELAY_SECONDS (optional):
#   retry settings for post-start HTTP health probes.
# ----------------------------------------------------------------------------

DEPLOY_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
ENV_FILE=${ENV_FILE:-"$DEPLOY_DIR/.env"}

if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

DATA_ROOT=${DATA_ROOT:?DATA_ROOT is required}
DEPLOY_GROUP=${DEPLOY_GROUP:-}
OPERATION_LOCK_HELPER="$DEPLOY_DIR/scripts/lib/operation-lock.sh"
MAINTENANCE_FLAG_FILE=${MAINTENANCE_FLAG_FILE:-"$DATA_ROOT/runtime/maintenance"}
MAINTENANCE_HELPER="$DEPLOY_DIR/scripts/maintenance.sh"
SOURCE_REVISION=${SOURCE_REVISION:-unknown}
# Derive the revision from the checkout when the environment leaves it unset.
if [ "$SOURCE_REVISION" = unknown ] && command -v git >/dev/null 2>&1; then
    SOURCE_REVISION=$(git -C "$DEPLOY_DIR" rev-parse --short HEAD 2>/dev/null || printf 'unknown')
fi
export SOURCE_REVISION
MAINTENANCE_TOKEN=
MAINTENANCE_FINISH_COMMAND=
MAINTENANCE_STARTED=false

# shellcheck disable=SC1090
. "$OPERATION_LOCK_HELPER"

# shellcheck source=lib/compose.sh
. "$DEPLOY_DIR/scripts/lib/compose.sh"

# Trap handler for failures:
# - prints a recovery hint when deployment fails
# - releases the shared operation lock when this process owns it
# - preserves the original exit code
fail_recovery_hint() {
    status=$1
    trap - EXIT INT TERM
    if [ "$status" -ne 0 ]; then
        if [ "$MAINTENANCE_STARTED" = true ]; then
            echo "deployment failed; maintenance mode remains enabled" >&2
        else
            echo "deployment failed before this attempt enabled or resumed maintenance mode" >&2
        fi
        if [ -n "$MAINTENANCE_FINISH_COMMAND" ]; then
            printf 'after recovery, run: %s\n' "$MAINTENANCE_FINISH_COMMAND" >&2
        fi
    fi
    if [ "$OPERATION_LOCK_ACQUIRED" = true ]; then
        release_operation_lock
    fi
    exit "$status"
}

trap 'fail_recovery_hint "$?"' EXIT
trap 'fail_recovery_hint 130' INT
trap 'fail_recovery_hint 143' TERM

# Delegates configuration validation to a dedicated script.
validate_config() {
    "$DEPLOY_DIR/scripts/validate-config.sh"
}

# Builds all required Docker images based on compose configuration.
build_images() {
    cd "$DEPLOY_DIR"
    compose build
}

# Ensures the database container is started and accepting connections before
# deployment enters maintenance mode.
ensure_database_ready() {
    cd "$DEPLOY_DIR"
    compose up -d postgres

    attempts=${POSTGRES_READY_ATTEMPTS:-30}
    delay_seconds=${POSTGRES_READY_DELAY_SECONDS:-2}
    attempt=1
    while [ "$attempt" -le "$attempts" ]; do
        if compose exec -T postgres pg_isready \
            -U "$POSTGRES_USER" \
            -d "$POSTGRES_DB" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$delay_seconds"
        attempt=$((attempt + 1))
    done

    compose ps postgres >&2 || true
    echo "postgres did not become ready after ${attempts} attempts" >&2
    exit 1
}

# Verifies the configured PostgreSQL secret against the initialized database.
# This catches stale volumes initialized with an old password before maintenance.
verify_database_credentials() {
    cd "$DEPLOY_DIR"
    compose --profile backup run --rm --no-deps \
        --entrypoint /bin/sh backup -ec '
test -r "$POSTGRES_PASSWORD_FILE"
export PGPASSWORD
PGPASSWORD=$(cat "$POSTGRES_PASSWORD_FILE")
psql \
    --host="$POSTGRES_HOST" \
    --port="${POSTGRES_PORT:-5432}" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --set=ON_ERROR_STOP=1 \
    --command="select 1" >/dev/null
'
}

# Enables maintenance mode and publishes a finite alert-suppression deadline.
enable_maintenance() {
    MAINTENANCE_TOKEN=$(SOURCE_REVISION="$SOURCE_REVISION" "$MAINTENANCE_HELPER" start deploy "${DEPLOY_MAINTENANCE_TIMEOUT_SECONDS:-3600}")
    MAINTENANCE_STARTED=true
    MAINTENANCE_FINISH_COMMAND=$(ENV_FILE="$ENV_FILE" "$MAINTENANCE_HELPER" finish-command deploy "$MAINTENANCE_TOKEN")
}

# Creates a backup via the dedicated compose backup profile.
run_backup() {
    if [ "${SKIP_BACKUP:-false}" = "true" ]; then
        echo "skipping backup because SKIP_BACKUP=true" >&2
        return 0
    fi

    cd "$DEPLOY_DIR"
    compose --profile backup run --rm backup
}

# Runs DB migrations in an ephemeral container.
run_migrations() {
    cd "$DEPLOY_DIR"
    compose run --rm django-migrate
}

# Repopulates all configured GeneralManager search indexes in place.
rebuild_search_indexes() {
    cd "$DEPLOY_DIR"
    compose --profile deployment run --rm --no-deps search-index
}

# Starts/updates services in detached mode, applies replicas,
# and removes orphaned containers.
start_services() {
    cd "$DEPLOY_DIR"
    compose up -d --remove-orphans \
        --scale "web=${WEB_REPLICAS:-2}" \
        --scale "celery-worker=${CELERY_REPLICAS:-1}"
}

wait_for_http() {
    service=$1
    url=$2
    shift 2

    attempts=${HEALTHCHECK_ATTEMPTS:-30}
    delay_seconds=${HEALTHCHECK_DELAY_SECONDS:-2}
    attempt=1
    while [ "$attempt" -le "$attempts" ]; do
        if compose exec -T "$service" curl --fail --silent "$@" "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$delay_seconds"
        attempt=$((attempt + 1))
    done

    compose ps "$service" >&2 || true
    echo "$service health check failed for $url after ${attempts} attempts" >&2
    exit 1
}

wait_for_public_graphql() {
    attempts=${HEALTHCHECK_ATTEMPTS:-30}
    delay_seconds=${HEALTHCHECK_DELAY_SECONDS:-2}
    attempt=1
    graphql_success='"data":{"__typename":"Query"}'
    while [ "$attempt" -le "$attempts" ]; do
        response=$(compose exec -T nginx curl --fail --silent --show-error \
            --connect-timeout 3 \
            --max-time 10 \
            --insecure \
            --header "Host: $APP_DOMAIN" \
            --get \
            --data-urlencode 'query=query HealthProbe { __typename }' \
            --data-urlencode 'operationName=HealthProbe' \
            https://127.0.0.1/graphql/ 2>/dev/null) || response=
        case "$response" in
            *"$graphql_success"*) return 0 ;;
        esac
        sleep "$delay_seconds"
        attempt=$((attempt + 1))
    done

    compose ps nginx >&2 || true
    echo "public GraphQL HealthProbe failed after ${attempts} attempts" >&2
    exit 1
}

# Minimal runtime checks:
# - shows compose status
# - checks nginx health endpoint
# - checks app liveness/readiness
verify_health() {
    cd "$DEPLOY_DIR"
    compose ps
    wait_for_http nginx https://127.0.0.1/nginx-healthz --insecure
    wait_for_http web http://127.0.0.1:8000/health/live/ --header "Host: $APP_DOMAIN"
    wait_for_http web http://127.0.0.1:8000/health/ready/ --header "Host: $APP_DOMAIN"
    wait_for_public_graphql
}

# Publishes deployment metadata and disables maintenance only after success.
publish_deploy() {
    SOURCE_REVISION="$SOURCE_REVISION" "$MAINTENANCE_HELPER" publish-deploy
}

disable_maintenance() {
    SOURCE_REVISION="$SOURCE_REVISION" "$MAINTENANCE_HELPER" finish deploy "$MAINTENANCE_TOKEN"
}

# Clears Django's configured default cache after a successful deployment.
# This runs as best-effort to avoid marking an otherwise successful deploy as failed.
reset_application_cache() {
    cd "$DEPLOY_DIR"
    if ! compose exec -T web python manage.py shell -c \
        'from django.core.cache import cache; cache.clear()'; then
        echo "warning: failed to clear application cache" >&2
    fi
}

acquire_operation_lock deploy
validate_config
build_images
ensure_database_ready
verify_database_credentials
enable_maintenance
run_backup
run_migrations
rebuild_search_indexes
start_services
verify_health
publish_deploy
disable_maintenance
reset_application_cache
