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

: "${DATA_ROOT:?DATA_ROOT is required}"
: "${APP_DOMAIN:?APP_DOMAIN is required}"
: "${MONITORING_DOMAIN:?MONITORING_DOMAIN is required}"

validate_domain() {
    name=$1
    value=$2

    case "$value" in
        .*|*.|-*|*-|*..*|*.-*|*-.*|*[!A-Za-z0-9.-]*)
            echo "$name must contain valid DNS labels" >&2
            exit 1
            ;;
    esac
}

validate_mail() {
    name=$1
    value=$2

    case "$value" in
        ""|*[!A-Za-z0-9@._+,-]*)
            echo "$name must contain only safe mail characters" >&2
            exit 1
            ;;
    esac
}

validate_bool() {
    name=$1
    value=$2

    case "$value" in
        true|false) ;;
        *)
            echo "$name must be true or false" >&2
            exit 1
            ;;
    esac
}

validate_host_port() {
    name=$1
    value=$2

    case "$value" in
        ""|*[!A-Za-z0-9._:-]*|*:)
            echo "$name must be a safe host and numeric port" >&2
            exit 1
            ;;
        *:*)
            host=${value%:*}
            port=${value##*:}
            ;;
        *)
            echo "$name must be a safe host and numeric port" >&2
            exit 1
            ;;
    esac
    case "$host:$port" in
        :*|*:""|*:*[!0-9]*)
            echo "$name must be a safe host and numeric port" >&2
            exit 1
            ;;
    esac
}

validate_safe_url() {
    name=$1
    value=$2

    case "$value" in
        http://*|https://*) ;;
        *)
            echo "$name must be an http(s) URL" >&2
            exit 1
            ;;
    esac
    case "$value" in
        *[!A-Za-z0-9:/._%?=-]*)
            echo "$name must contain only safe URL characters" >&2
            exit 1
            ;;
    esac
}

validate_domain APP_DOMAIN "$APP_DOMAIN"
validate_domain MONITORING_DOMAIN "$MONITORING_DOMAIN"
ALERT_TEAMS_ENABLED=${ALERT_TEAMS_ENABLED:-true}
ALERT_SMTP_AUTH_ENABLED=${ALERT_SMTP_AUTH_ENABLED:-true}
ALERT_SMTP_REQUIRE_TLS=${ALERT_SMTP_REQUIRE_TLS:-true}
validate_bool ALERT_TEAMS_ENABLED "$ALERT_TEAMS_ENABLED"
validate_bool ALERT_SMTP_AUTH_ENABLED "$ALERT_SMTP_AUTH_ENABLED"
validate_bool ALERT_SMTP_REQUIRE_TLS "$ALERT_SMTP_REQUIRE_TLS"
validate_host_port ALERT_SMTP_SMARTHOST "${ALERT_SMTP_SMARTHOST:-}"
validate_mail ALERT_SMTP_FROM "${ALERT_SMTP_FROM:-}"
if [ "$ALERT_SMTP_AUTH_ENABLED" = true ]; then
    validate_mail ALERT_SMTP_USERNAME "${ALERT_SMTP_USERNAME:-}"
fi
validate_mail ALERT_EMAIL_TO "${ALERT_EMAIL_TO:-}"
validate_safe_url OBSERVABILITY_RUNBOOK_BASE_URL "${OBSERVABILITY_RUNBOOK_BASE_URL:-}"

export APP_DOMAIN MONITORING_DOMAIN ALERT_TEAMS_ENABLED
export ALERT_SMTP_SMARTHOST ALERT_SMTP_FROM
export ALERT_SMTP_USERNAME ALERT_SMTP_AUTH_ENABLED ALERT_SMTP_REQUIRE_TLS
export ALERT_EMAIL_TO OBSERVABILITY_RUNBOOK_BASE_URL

PROMETHEUS_OUTPUT_DIR=$DATA_ROOT/runtime/prometheus
ALERTMANAGER_OUTPUT_DIR=$DATA_ROOT/runtime/alertmanager
OUTPUT_ONE=$PROMETHEUS_OUTPUT_DIR/blackbox-targets.yml
OUTPUT_TWO=$PROMETHEUS_OUTPUT_DIR/alerts.yml
OUTPUT_THREE=$ALERTMANAGER_OUTPUT_DIR/alertmanager.yml
TEMP_ONE=
TEMP_TWO=
TEMP_THREE=
BACKUP_ONE=
BACKUP_TWO=
BACKUP_THREE=
ORIGINAL_ONE_EXISTED=0
ORIGINAL_TWO_EXISTED=0
ORIGINAL_THREE_EXISTED=0
COMMITTED_ONE=0
COMMITTED_TWO=0
COMMITTED_THREE=0
PUBLISH_COMPLETE=0

validate_destination() {
    destination=$1

    if [ -L "$destination" ] || { [ -e "$destination" ] && [ ! -f "$destination" ]; }; then
        echo "render destination must be a regular non-symlink file: $destination" >&2
        exit 1
    fi
}

remove_if_set() {
    path=$1
    if [ -n "$path" ]; then
        rm -f "$path"
    fi
}

rollback() {
    status=$?
    trap - 0 HUP INT TERM
    set +e

    if [ "$PUBLISH_COMPLETE" -eq 0 ]; then
        if [ "$COMMITTED_THREE" -eq 1 ]; then
            rm -f "$OUTPUT_THREE"
        fi
        if [ "$ORIGINAL_THREE_EXISTED" -eq 1 ]; then
            mv "$BACKUP_THREE" "$OUTPUT_THREE"
            BACKUP_THREE=
        fi
        if [ "$COMMITTED_TWO" -eq 1 ]; then
            rm -f "$OUTPUT_TWO"
        fi
        if [ "$ORIGINAL_TWO_EXISTED" -eq 1 ]; then
            mv "$BACKUP_TWO" "$OUTPUT_TWO"
            BACKUP_TWO=
        fi
        if [ "$COMMITTED_ONE" -eq 1 ]; then
            rm -f "$OUTPUT_ONE"
        fi
        if [ "$ORIGINAL_ONE_EXISTED" -eq 1 ]; then
            mv "$BACKUP_ONE" "$OUTPUT_ONE"
            BACKUP_ONE=
        fi
    fi

    remove_if_set "$TEMP_ONE"
    remove_if_set "$TEMP_TWO"
    remove_if_set "$TEMP_THREE"
    remove_if_set "$BACKUP_ONE"
    remove_if_set "$BACKUP_TWO"
    remove_if_set "$BACKUP_THREE"
    exit "$status"
}

render_template() {
    source=$1
    staged_output=$2

    awk '
        {
            if ($0 ~ /[[:space:]]# TEAMS_ONLY[[:space:]]*$/) {
                if (ENVIRON["ALERT_TEAMS_ENABLED"] != "true") {
                    next
                }
                sub(/[[:space:]]+# TEAMS_ONLY[[:space:]]*$/, "")
            }
            if ($0 ~ /[[:space:]]# SMTP_AUTH_ONLY[[:space:]]*$/) {
                if (ENVIRON["ALERT_SMTP_AUTH_ENABLED"] != "true") {
                    next
                }
                sub(/[[:space:]]+# SMTP_AUTH_ONLY[[:space:]]*$/, "")
            }
            gsub(/__APP_DOMAIN__/, ENVIRON["APP_DOMAIN"])
            gsub(/__MONITORING_DOMAIN__/, ENVIRON["MONITORING_DOMAIN"])
            gsub(/__ALERT_SMTP_SMARTHOST__/, ENVIRON["ALERT_SMTP_SMARTHOST"])
            gsub(/__ALERT_SMTP_FROM__/, ENVIRON["ALERT_SMTP_FROM"])
            gsub(/__ALERT_SMTP_USERNAME__/, ENVIRON["ALERT_SMTP_USERNAME"])
            gsub(/__ALERT_SMTP_REQUIRE_TLS__/, ENVIRON["ALERT_SMTP_REQUIRE_TLS"])
            gsub(/__ALERT_EMAIL_TO__/, ENVIRON["ALERT_EMAIL_TO"])
            gsub(/__RUNBOOK_BASE_URL__/, ENVIRON["OBSERVABILITY_RUNBOOK_BASE_URL"])
            print
        }
    ' "$source" >"$staged_output"
    chmod 0644 "$staged_output"
}

validate_destination "$OUTPUT_ONE"
validate_destination "$OUTPUT_TWO"
validate_destination "$OUTPUT_THREE"
mkdir -p "$PROMETHEUS_OUTPUT_DIR" "$ALERTMANAGER_OUTPUT_DIR"

trap rollback 0
trap 'exit 1' HUP INT TERM

TEMP_ONE=$(mktemp "${OUTPUT_ONE}.render.XXXXXX")
TEMP_TWO=$(mktemp "${OUTPUT_TWO}.render.XXXXXX")
TEMP_THREE=$(mktemp "${OUTPUT_THREE}.render.XXXXXX")
render_template "$DEPLOY_DIR/prometheus/blackbox-targets.yml.tmpl" "$TEMP_ONE"
render_template "$DEPLOY_DIR/prometheus/alerts.yml.tmpl" "$TEMP_TWO"
render_template "$DEPLOY_DIR/alertmanager/alertmanager.yml.tmpl" "$TEMP_THREE"

if [ -e "$OUTPUT_ONE" ]; then
    BACKUP_ONE=$(mktemp "${OUTPUT_ONE}.backup.XXXXXX")
    cp -p "$OUTPUT_ONE" "$BACKUP_ONE"
    ORIGINAL_ONE_EXISTED=1
fi
if [ -e "$OUTPUT_TWO" ]; then
    BACKUP_TWO=$(mktemp "${OUTPUT_TWO}.backup.XXXXXX")
    cp -p "$OUTPUT_TWO" "$BACKUP_TWO"
    ORIGINAL_TWO_EXISTED=1
fi
if [ -e "$OUTPUT_THREE" ]; then
    BACKUP_THREE=$(mktemp "${OUTPUT_THREE}.backup.XXXXXX")
    cp -p "$OUTPUT_THREE" "$BACKUP_THREE"
    ORIGINAL_THREE_EXISTED=1
fi

COMMITTED_ONE=1
mv "$TEMP_ONE" "$OUTPUT_ONE"
TEMP_ONE=
# PUBLISH_ONE_COMPLETE
COMMITTED_TWO=1
mv "$TEMP_TWO" "$OUTPUT_TWO"
TEMP_TWO=
# PUBLISH_TWO_COMPLETE
COMMITTED_THREE=1
mv "$TEMP_THREE" "$OUTPUT_THREE"
TEMP_THREE=
PUBLISH_COMPLETE=1

remove_if_set "$BACKUP_ONE"
BACKUP_ONE=
remove_if_set "$BACKUP_TWO"
BACKUP_TWO=
remove_if_set "$BACKUP_THREE"
BACKUP_THREE=
trap - 0 HUP INT TERM
