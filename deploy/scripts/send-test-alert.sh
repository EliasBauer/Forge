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

test "${CONFIRM_ALERT_NOTIFICATION_TEST:-false}" = true || {
    printf '%s\n' 'Set CONFIRM_ALERT_NOTIFICATION_TEST=true to send the test alert.' >&2
    exit 2
}

# shellcheck source=lib/compose.sh
. "$DEPLOY_DIR/scripts/lib/compose.sh"

post_alert() {
    payload=$1
    compose --profile observability exec -T alertmanager wget \
        --quiet \
        --server-response \
        --output-document=/dev/null \
        '--header=Content-Type: application/json' \
        --post-data="$payload" \
        http://127.0.0.1:9093/api/v2/alerts
}

firing='[{"labels":{"alertname":"ForgeNotificationTest","service":"observability","severity":"warning","notification_scope":"always","alert_family":"notification-test"},"annotations":{"summary":"Deliberate Forge receiver test","impact":"No user impact; an operator requested this test.","first_action":"Confirm receipt in Teams and email."},"startsAt":"2026-01-01T00:00:00Z","endsAt":"2099-01-01T00:00:00Z"}]'
resolved='[{"labels":{"alertname":"ForgeNotificationTest","service":"observability","severity":"warning","notification_scope":"always","alert_family":"notification-test"},"annotations":{"summary":"Deliberate Forge receiver test","impact":"No user impact; an operator requested this test.","first_action":"Confirm receipt in Teams and email."},"startsAt":"2026-01-01T00:00:00Z","endsAt":"2026-01-01T00:00:01Z"}]'

cd "$DEPLOY_DIR"
post_alert "$firing"
sleep 5
post_alert "$resolved"

printf '%s\n' 'test alert firing and resolved notifications submitted'
