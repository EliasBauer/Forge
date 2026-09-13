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

cd "$DEPLOY_DIR"
compose --profile observability run --rm --no-deps --entrypoint /bin/promtool \
    prometheus check config /etc/prometheus/prometheus.yml
compose --profile observability run --rm --no-deps --entrypoint /bin/amtool \
    alertmanager check-config --enable-feature=utf8-strict-mode \
    /etc/alertmanager/alertmanager.yml
compose --profile observability run --rm --no-deps --entrypoint /usr/bin/loki \
    loki -verify-config=true -config.file=/etc/loki/loki.yml
compose --profile observability run --rm --no-deps --entrypoint /bin/alloy \
    alloy validate /etc/alloy/config.alloy
compose --profile observability run --rm --no-deps --entrypoint /bin/blackbox_exporter \
    blackbox-exporter --config.file=/etc/blackbox_exporter/config.yml --config.check
