#!/bin/sh
set -eu

DEPLOY_DIR=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd -P)
ENV_FILE=${ENV_FILE:-"$DEPLOY_DIR/.env"}

if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

# shellcheck source=lib/compose.sh
. "$DEPLOY_DIR/scripts/lib/compose.sh"

"$DEPLOY_DIR/scripts/render-observability-config.sh"
"$DEPLOY_DIR/scripts/validate-config.sh"
"$DEPLOY_DIR/scripts/validate-observability-config.sh"
cd "$DEPLOY_DIR"
# These services load bind-mounted configuration or provisioning at startup.
# Recreate them only after the complete rendered configuration has validated.
compose --profile observability --profile administration up -d \
    --force-recreate --no-deps --no-build \
    prometheus alertmanager grafana loki alloy blackbox-exporter
compose --profile observability --profile administration up -d --no-deps --no-build \
    prometheus alertmanager grafana loki alloy node-exporter pgbouncer-exporter \
    blackbox-exporter postgres-exporter redis-exporter celery-exporter \
    nginx-exporter pushgateway pgadmin
compose ps prometheus alertmanager grafana loki alloy node-exporter pgbouncer-exporter blackbox-exporter postgres-exporter redis-exporter celery-exporter nginx-exporter pushgateway pgadmin
