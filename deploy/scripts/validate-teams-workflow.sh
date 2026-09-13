#!/bin/sh
set -eu

ALERT_TEAMS_ENABLED=${ALERT_TEAMS_ENABLED:-true}
: "${TEAMS_WORKFLOW_URL_FILE:?TEAMS_WORKFLOW_URL_FILE is required}"

fail() {
    echo "preflight failed: $*" >&2
    exit 1
}

case "$ALERT_TEAMS_ENABLED" in
    true|false) ;;
    *) fail "ALERT_TEAMS_ENABLED must be true or false" ;;
esac

if [ -L "$TEAMS_WORKFLOW_URL_FILE" ] || [ ! -f "$TEAMS_WORKFLOW_URL_FILE" ]; then
    fail "Teams Workflow secret must be a regular non-symlink file: $TEAMS_WORKFLOW_URL_FILE"
fi
test -r "$TEAMS_WORKFLOW_URL_FILE" || {
    fail "Teams Workflow secret is not readable: $TEAMS_WORKFLOW_URL_FILE"
}

if [ "$ALERT_TEAMS_ENABLED" = false ]; then
    exit 0
fi

workflow_url=$(cat "$TEAMS_WORKFLOW_URL_FILE")
test -n "$workflow_url" || {
    fail "Teams Workflow secret is empty: $TEAMS_WORKFLOW_URL_FILE"
}

case "$workflow_url" in
    CHANGE_ME|CHANGE_ME_|*REPLACE_WITH*)
        fail "Teams Workflow secret still contains a placeholder: $TEAMS_WORKFLOW_URL_FILE"
        ;;
esac

case "$workflow_url" in
    *[[:space:]]*)
        fail "Teams Workflow secret must not contain whitespace: $TEAMS_WORKFLOW_URL_FILE"
        ;;
    https://?*)
        ;;
    *)
        fail "Teams Workflow secret must contain an HTTPS URL: $TEAMS_WORKFLOW_URL_FILE"
        ;;
esac

case "${workflow_url#https://}" in
    ""|/*)
        fail "Teams Workflow secret must contain an HTTPS URL with a host: $TEAMS_WORKFLOW_URL_FILE"
        ;;
esac
