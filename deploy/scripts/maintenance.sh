#!/bin/sh
set -eu

DEPLOY_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
ENV_FILE=${ENV_FILE:-"$DEPLOY_DIR/.env"}
ENV_FILE=$(cd -- "$(dirname -- "$ENV_FILE")" && pwd -P)/$(basename -- "$ENV_FILE")
OPERATION_LOCK_HELPER="$DEPLOY_DIR/scripts/lib/operation-lock.sh"

if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

# shellcheck disable=SC1090
. "$OPERATION_LOCK_HELPER"

usage() {
    cat >&2 <<EOF
Usage: $0 start REASON DURATION_SECONDS
       $0 finish REASON TOKEN
       $0 finish-command REASON TOKEN
       $0 publish-deploy
       $0 reset-all
       $0 status

REASON must be deploy or restore.
EOF
}

fail() {
    echo "maintenance helper failed: $*" >&2
    exit 1
}

validate_reason() {
    case "$1" in
        deploy | restore) ;;
        *) fail "reason must be deploy or restore" ;;
    esac
}

validate_safe_value() {
    name=$1
    value=$2
    max_length=$3
    case "$value" in
        "" | *[!A-Za-z0-9._-]*)
            fail "$name must contain only A-Za-z0-9._-"
            ;;
    esac
    test "${#value}" -le "$max_length" || fail "$name is too long"
}

validate_revision() {
    validate_safe_value SOURCE_REVISION "$SOURCE_REVISION" 128
}

validate_deploy_group() {
    test -n "$DEPLOY_GROUP" || fail "DEPLOY_GROUP is required"
    validate_safe_value DEPLOY_GROUP "$DEPLOY_GROUP" 128
}

fail_inconsistent_state() {
    fail "$1; run ./scripts/maintenance.sh status and, only after confirming no operation is live, run CONFIRM_RESET_ALL_LEASES=true ./scripts/maintenance.sh reset-all"
}

is_safe_lease_value() {
    value=$1
    case "$value" in
        "" | *[!A-Za-z0-9._-]*) return 1 ;;
    esac
    test "${#value}" -le 128
}

validate_token() {
    validate_safe_value token "$1" 128
}

validate_duration() {
    case "$1" in
        "" | *[!0-9]*) fail "duration must be numeric" ;;
        0[0-9]*) fail "duration must not have a leading zero" ;;
    esac
    test "$1" -ge 60 && test "$1" -le 172800 ||
        fail "duration must be between 60 and 172800 seconds"
}

install_signal_exit_traps() {
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
}

shell_quote() {
    quoted=$(printf '%s' "$1" | sed "s/'/'\\\\''/g")
    printf "'%s'" "$quoted"
}

remove_lease() {
    rm -f "$LEASE_DIR/reason" "$LEASE_DIR/token" "$LEASE_DIR/revision"
    rmdir "$LEASE_DIR"
}

restore_lease() {
    if [ ! -d "$LEASE_DIR" ]; then
        mkdir "$LEASE_DIR" || return 1
    fi
    chgrp "$DEPLOY_GROUP" "$LEASE_DIR" || return 1
    chmod 0770 "$LEASE_DIR" || return 1
    printf '%s\n' "$ACTIVE_REASON" > "$LEASE_DIR/reason" || return 1
    printf '%s\n' "$ACTIVE_TOKEN" > "$LEASE_DIR/token" || return 1
    printf '%s\n' "$ACTIVE_REVISION" > "$LEASE_DIR/revision" || return 1
    chgrp "$DEPLOY_GROUP" \
        "$LEASE_DIR/reason" "$LEASE_DIR/token" "$LEASE_DIR/revision" || return 1
    chmod 0660 "$LEASE_DIR/reason" "$LEASE_DIR/token" "$LEASE_DIR/revision"
}

cleanup_temporary_files() {
    test -z "${METRICS_TMP:-}" || rm -f "$METRICS_TMP"
    test -z "${FLAG_TMP:-}" || rm -f "$FLAG_TMP"
    test -z "${METRICS_BACKUP:-}" || rm -f "$METRICS_BACKUP"
    test -z "${FLAG_BACKUP:-}" || rm -f "$FLAG_BACKUP"
    test -z "${LEASE_TMP:-}" || rm -f "$LEASE_TMP"
    test -z "${REVISION_TMP:-}" || rm -f "$REVISION_TMP"
    test -z "${REVISION_BACKUP:-}" || rm -f "$REVISION_BACKUP"
}

reset_path_exists() {
    test -e "$1" || test -L "$1"
}

restore_reset_path() {
    reset_restore_source=$1
    reset_restore_target=$2
    test -z "$reset_restore_source" ||
        ! reset_path_exists "$reset_restore_source" ||
        mv "$reset_restore_source" "$reset_restore_target"
}

rollback_inflight_reset_quarantine() {
    test -z "${RESET_INFLIGHT_QUARANTINE_PATH:-}" ||
        ! reset_path_exists "$RESET_INFLIGHT_QUARANTINE_PATH" || {
        if reset_path_exists "$RESET_INFLIGHT_QUARANTINE_TARGET"; then
            rmdir "$RESET_INFLIGHT_QUARANTINE_PATH" || true
        else
            mv "$RESET_INFLIGHT_QUARANTINE_PATH" \
                "$RESET_INFLIGHT_QUARANTINE_TARGET" || true
        fi
    }
    RESET_INFLIGHT_QUARANTINE_PATH=
    RESET_INFLIGHT_QUARANTINE_TARGET=
    RESET_INFLIGHT_QUARANTINE_KIND=
}

rollback_reset() {
    rollback_inflight_reset_quarantine || true
    if [ "${RESET_METRICS_TRANSITION_ATTEMPTED:-false}" = "true" ]; then
        rm -f "$MAINTENANCE_METRICS" || true
    fi
    restore_reset_path "${RESET_METRICS_BACKUP:-}" "$MAINTENANCE_METRICS" || true
    RESET_METRICS_BACKUP=
    restore_reset_path \
        "${RESET_POSTGRES_LOCK_QUARANTINE:-}" "$POSTGRES_RESTORE_LOCK_DIR" || true
    RESET_POSTGRES_LOCK_QUARANTINE=
    restore_reset_path \
        "${RESET_DEPLOY_LOCK_QUARANTINE:-}" "$DEPLOY_LOCK_DIR" || true
    RESET_DEPLOY_LOCK_QUARANTINE=
    restore_reset_path "${RESET_LEASE_QUARANTINE:-}" "$LEASE_DIR" || true
    RESET_LEASE_QUARANTINE=
    restore_reset_path \
        "${RESET_FLAG_QUARANTINE:-}" "$MAINTENANCE_FLAG_FILE" || true
    RESET_FLAG_QUARANTINE=
}

cleanup_reset_created_directories() {
    if [ "${RESET_CREATED_TEXTFILE_DIR:-false}" = "true" ]; then
        rmdir "$TEXTFILE_DIR" || true
    fi
    if [ "${RESET_CREATED_RUNTIME_DIR:-false}" = "true" ]; then
        rmdir "$RESET_RUNTIME_DIR" || true
    fi
}

restore_metrics_backup() {
    rm -f "$MAINTENANCE_METRICS" || return 1
    mv "$METRICS_BACKUP" "$MAINTENANCE_METRICS" || return 1
    METRICS_BACKUP=
    chgrp "$DEPLOY_GROUP" "$MAINTENANCE_METRICS" || return 1
    chmod 0644 "$MAINTENANCE_METRICS"
}

restore_revision_backup() {
    rm -f "$LEASE_DIR/revision" || return 1
    mv "$REVISION_BACKUP" "$LEASE_DIR/revision" || return 1
    REVISION_BACKUP=
    chgrp "$DEPLOY_GROUP" "$LEASE_DIR/revision" || return 1
    chmod 0660 "$LEASE_DIR/revision"
}

rollback() {
    status=${1:-$?}
    trap '' EXIT HUP INT TERM

    if [ "${TRANSACTION:-}" = "start" ]; then
        if [ "${FLAG_TRANSITION_ATTEMPTED:-false}" = "true" ]; then
            rm -f "$MAINTENANCE_FLAG_FILE" || true
        fi
        if [ "${METRICS_TRANSITION_ATTEMPTED:-false}" = "true" ]; then
            rm -f "$MAINTENANCE_METRICS" || true
            if [ "${PREVIOUS_METRICS:-false}" = "true" ]; then
                restore_metrics_backup || true
            fi
        fi
        if [ "${ACQUIRED_LEASE:-false}" = "true" ] && [ -d "$LEASE_DIR" ]; then
            if [ -n "${LEASE_TMP:-}" ]; then
                rm -f "$LEASE_TMP" || true
                LEASE_TMP=
            fi
            remove_lease || true
        fi
    elif [ "${TRANSACTION:-}" = "resume" ]; then
        if [ "${METRICS_TRANSITION_ATTEMPTED:-false}" = "true" ]; then
            restore_metrics_backup || true
        fi
        if [ "${REVISION_TRANSITION_ATTEMPTED:-false}" = "true" ]; then
            restore_revision_backup || true
        fi
    elif [ "${TRANSACTION:-}" = "finish" ]; then
        if [ "${METRICS_TRANSITION_ATTEMPTED:-false}" = "true" ]; then
            restore_metrics_backup || true
        fi
        if [ "${FLAG_TRANSITION_ATTEMPTED:-false}" = "true" ]; then
            rm -f "$MAINTENANCE_FLAG_FILE" || true
            mv "$FLAG_BACKUP" "$MAINTENANCE_FLAG_FILE" || true
            FLAG_BACKUP=
            chgrp "$DEPLOY_GROUP" "$MAINTENANCE_FLAG_FILE" || true
            chmod 0644 "$MAINTENANCE_FLAG_FILE" || true
        fi
        restore_lease || true
    elif [ "${TRANSACTION:-}" = "reset" ]; then
        rollback_reset || true
    fi

    cleanup_temporary_files || true
    if [ "${TRANSACTION:-}" = "reset" ]; then
        cleanup_reset_created_directories || true
    fi
    release_operation_lock || true
    exit "$status"
}

finish_transaction() {
    status=$?
    trap '' EXIT HUP INT TERM
    if [ "${TRANSACTION:-}" = "reset" ] &&
        [ "${TRANSACTION_COMMITTED:-false}" = "true" ]; then
        reset_cleanup_status=0
        cleanup_committed_reset || reset_cleanup_status=$?
        cleanup_temporary_files || true
        release_operation_lock || true
        if [ "$status" -eq 0 ] && [ "$reset_cleanup_status" -ne 0 ]; then
            status=$reset_cleanup_status
        fi
        exit "$status"
    fi
    if [ "$status" -eq 0 ] && [ "${TRANSACTION_COMMITTED:-false}" = "true" ]; then
        TRANSACTION=
        cleanup_temporary_files || true
        release_operation_lock || true
        exit 0
    fi
    rollback "$status"
}

install_transaction_trap() {
    trap finish_transaction EXIT
    install_signal_exit_traps
}

backup_metrics() {
    if [ -f "$MAINTENANCE_METRICS" ]; then
        METRICS_BACKUP=$(mktemp "$TEXTFILE_DIR/.forge_maintenance.rollback.XXXXXX")
        cp -p "$MAINTENANCE_METRICS" "$METRICS_BACKUP"
        chgrp "$DEPLOY_GROUP" "$METRICS_BACKUP"
        chmod 0644 "$METRICS_BACKUP"
        PREVIOUS_METRICS=true
    fi
}

stage_maintenance_metrics() {
    mode=$1
    reason=$2
    started=$3
    suppress_until=$4
    revision=$5

    METRICS_TMP=$(mktemp "$TEXTFILE_DIR/.forge_maintenance.prom.XXXXXX")
    {
        printf 'forge_maintenance_mode %s\n' "$mode"
        printf 'forge_maintenance_started_timestamp_seconds %s\n' "$started"
        printf 'forge_maintenance_suppress_until_timestamp_seconds %s\n' "$suppress_until"
        printf 'forge_maintenance_info{reason="%s",revision="%s"} 1\n' \
            "$reason" "$revision"
    } > "$METRICS_TMP"
    chgrp "$DEPLOY_GROUP" "$METRICS_TMP"
    chmod 0644 "$METRICS_TMP"
}

write_lease_file() {
    name=$1
    value=$2
    LEASE_TMP=$(mktemp "$LEASE_DIR/.${name}.XXXXXX")
    printf '%s\n' "$value" > "$LEASE_TMP"
    chgrp "$DEPLOY_GROUP" "$LEASE_TMP"
    chmod 0660 "$LEASE_TMP"
    mv "$LEASE_TMP" "$LEASE_DIR/$name"
    LEASE_TMP=
}

reject_unleased_active_state() {
    test ! -f "$MAINTENANCE_FLAG_FILE" ||
        fail_inconsistent_state "maintenance flag exists without an active lease"
    if [ -f "$MAINTENANCE_METRICS" ]; then
        validate_maintenance_metrics 0 "" "" ||
            fail_inconsistent_state "maintenance metrics are active or invalid without an active lease"
    fi
}

start_maintenance() {
    reason=$1
    duration=$2
    now=$(date -u +%s)
    suppress_until=$((now + duration))
    token="${reason}-${now}-$$"
    validate_token "$token"

    if [ -d "$LEASE_DIR" ]; then
        load_active_lease
        test "$reason" = "$ACTIVE_REASON" ||
            fail_inconsistent_state "active maintenance lease belongs to $ACTIVE_REASON"
        validate_complete_active_state
        resume_maintenance "$reason" "$duration"
        return
    fi
    reject_unleased_active_state
    mkdir -p "$TEXTFILE_DIR" "$(dirname "$MAINTENANCE_FLAG_FILE")"

    TRANSACTION=start
    install_transaction_trap
    mkdir "$LEASE_DIR" || fail "an active maintenance lease already exists"
    ACQUIRED_LEASE=true
    chgrp "$DEPLOY_GROUP" "$LEASE_DIR"
    chmod 0770 "$LEASE_DIR"
    write_lease_file reason "$reason"
    write_lease_file token "$token"
    write_lease_file revision "$SOURCE_REVISION"

    backup_metrics
    stage_maintenance_metrics 1 "$reason" "$now" "$suppress_until" "$SOURCE_REVISION"
    FLAG_TMP=$(mktemp "$(dirname "$MAINTENANCE_FLAG_FILE")/.maintenance.XXXXXX")
    printf '%s\n' "maintenance" > "$FLAG_TMP"
    chgrp "$DEPLOY_GROUP" "$FLAG_TMP"
    chmod 0644 "$FLAG_TMP"

    METRICS_TRANSITION_ATTEMPTED=true
    mv -f "$METRICS_TMP" "$MAINTENANCE_METRICS"
    # TEST_START_IMMEDIATE_AFTER_METRICS_MV
    METRICS_TMP=
    FLAG_TRANSITION_ATTEMPTED=true
    mv "$FLAG_TMP" "$MAINTENANCE_FLAG_FILE"
    # TEST_START_IMMEDIATE_AFTER_FLAG_MV
    FLAG_TMP=

    TRANSACTION_COMMITTED=true
    printf '%s\n' "$token"
}

load_active_lease() {
    test -d "$LEASE_DIR" || fail "no active maintenance lease"
    for lease_file in reason token revision; do
        test -f "$LEASE_DIR/$lease_file" && test -r "$LEASE_DIR/$lease_file" ||
            fail_inconsistent_state "active maintenance lease is incomplete"
        test "$(wc -l < "$LEASE_DIR/$lease_file" | tr -d ' ')" -eq 1 &&
            test "$(awk 'END { print NR }' "$LEASE_DIR/$lease_file")" -eq 1 ||
            fail_inconsistent_state "active maintenance lease is not canonical"
    done
    IFS= read -r ACTIVE_REASON < "$LEASE_DIR/reason"
    IFS= read -r ACTIVE_TOKEN < "$LEASE_DIR/token"
    IFS= read -r ACTIVE_REVISION < "$LEASE_DIR/revision"
    case "$ACTIVE_REASON" in
        deploy | restore) ;;
        *) fail_inconsistent_state "active maintenance lease has an invalid reason" ;;
    esac
    is_safe_lease_value "$ACTIVE_TOKEN" ||
        fail_inconsistent_state "active maintenance lease has an invalid token"
    is_safe_lease_value "$ACTIVE_REVISION" ||
        fail_inconsistent_state "active maintenance lease has an invalid revision"
}

validate_maintenance_metrics() {
    expected_mode=$1
    expected_reason=$2
    expected_revision=$3
    awk -v expected_mode="$expected_mode" \
        -v expected_reason="$expected_reason" \
        -v expected_revision="$expected_revision" '
        function is_finite_number(value) {
            return length(value) <= 64 && value ~ /^[0-9]+([.][0-9]+)?$/
        }
        $0 == "forge_maintenance_mode " expected_mode {
            mode_count++
            next
        }
        index($0, "forge_maintenance_started_timestamp_seconds ") == 1 {
            value = substr($0, length("forge_maintenance_started_timestamp_seconds ") + 1)
            if (!is_finite_number(value)) invalid = 1
            started_count++
            next
        }
        index($0, "forge_maintenance_suppress_until_timestamp_seconds ") == 1 {
            value = substr($0, length("forge_maintenance_suppress_until_timestamp_seconds ") + 1)
            if (!is_finite_number(value)) invalid = 1
            suppress_count++
            next
        }
        index($0, "forge_maintenance_info{") == 1 {
            if (expected_reason != "") {
                expected_info = "forge_maintenance_info{reason=\"" expected_reason \
                    "\",revision=\"" expected_revision "\"} 1"
                if ($0 != expected_info) invalid = 1
            } else if ($0 !~ /^forge_maintenance_info\{reason="(deploy|migration|restore|reset)",revision="[A-Za-z0-9._-]+"\} 1$/) {
                invalid = 1
            } else {
                revision = $0
                sub(/^forge_maintenance_info\{reason="(deploy|migration|restore|reset)",revision="/, "", revision)
                sub(/"\} 1$/, "", revision)
                if (length(revision) > 128) invalid = 1
            }
            info_count++
            next
        }
        { invalid = 1 }
        END {
            if (NR != 4 || mode_count != 1 || started_count != 1 ||
                    suppress_count != 1 || info_count != 1 || invalid) exit 1
        }
    ' "$MAINTENANCE_METRICS"
}

validate_complete_active_state() {
    test -f "$MAINTENANCE_FLAG_FILE" ||
        fail_inconsistent_state "active lease has no maintenance flag"
    test -f "$MAINTENANCE_METRICS" && validate_maintenance_metrics \
        1 "$ACTIVE_REASON" "$ACTIVE_REVISION" ||
        fail_inconsistent_state "active lease has no active maintenance metrics"
}

resume_maintenance() {
    reason=$1
    duration=$2
    now=$(date -u +%s)
    suppress_until=$((now + duration))

    TRANSACTION=resume
    install_transaction_trap
    backup_metrics
    REVISION_BACKUP=$(mktemp "$LEASE_DIR/.revision.rollback.XXXXXX")
    cp -p "$LEASE_DIR/revision" "$REVISION_BACKUP"
    chgrp "$DEPLOY_GROUP" "$REVISION_BACKUP"
    chmod 0660 "$REVISION_BACKUP"
    REVISION_TMP=$(mktemp "$LEASE_DIR/.revision.XXXXXX")
    printf '%s\n' "$SOURCE_REVISION" > "$REVISION_TMP"
    chgrp "$DEPLOY_GROUP" "$REVISION_TMP"
    chmod 0660 "$REVISION_TMP"
    stage_maintenance_metrics 1 "$reason" "$now" "$suppress_until" "$SOURCE_REVISION"

    REVISION_TRANSITION_ATTEMPTED=true
    # TEST_RESUME_BEFORE_REVISION_MV
    mv "$REVISION_TMP" "$LEASE_DIR/revision"
    # TEST_RESUME_IMMEDIATE_AFTER_REVISION_MV
    REVISION_TMP=
    METRICS_TRANSITION_ATTEMPTED=true
    # TEST_RESUME_BEFORE_METRICS_MV
    mv -f "$METRICS_TMP" "$MAINTENANCE_METRICS"
    # TEST_RESUME_IMMEDIATE_AFTER_METRICS_MV
    METRICS_TMP=

    TRANSACTION_COMMITTED=true
    printf '%s\n' "$ACTIVE_TOKEN"
}

finish_maintenance() {
    reason=$1
    token=$2
    load_active_lease
    test "$reason" = "$ACTIVE_REASON" || fail "reason does not match active lease"
    test "$token" = "$ACTIVE_TOKEN" || fail "token does not match active lease"
    validate_complete_active_state

    now=$(date -u +%s)
    suppress_until=$((now + 600))
    TRANSACTION=finish
    install_transaction_trap
    backup_metrics
    FLAG_BACKUP=$(mktemp "$(dirname "$MAINTENANCE_FLAG_FILE")/.maintenance.rollback.XXXXXX")
    cp -p "$MAINTENANCE_FLAG_FILE" "$FLAG_BACKUP"
    chgrp "$DEPLOY_GROUP" "$FLAG_BACKUP"
    chmod 0644 "$FLAG_BACKUP"
    stage_maintenance_metrics 0 "$reason" "$now" "$suppress_until" "$ACTIVE_REVISION"

    METRICS_TRANSITION_ATTEMPTED=true
    mv -f "$METRICS_TMP" "$MAINTENANCE_METRICS"
    # TEST_FINISH_IMMEDIATE_AFTER_METRICS_MV
    METRICS_TMP=
    FLAG_TRANSITION_ATTEMPTED=true
    rm -f "$MAINTENANCE_FLAG_FILE"
    # TEST_FINISH_IMMEDIATE_AFTER_FLAG_REMOVE
    remove_lease
    # TEST_FINISH_IMMEDIATE_AFTER_LEASE_REMOVE

    TRANSACTION_COMMITTED=true
}

preflight_reset_parent() {
    reset_preflight_parent=$(dirname "$1")
    while ! reset_path_exists "$reset_preflight_parent"; do
        reset_preflight_next=$(dirname "$reset_preflight_parent")
        test "$reset_preflight_next" != "$reset_preflight_parent" ||
            fail "cannot find an existing parent for $1"
        reset_preflight_parent=$reset_preflight_next
    done
    test -d "$reset_preflight_parent" &&
        test -w "$reset_preflight_parent" &&
        test -x "$reset_preflight_parent" ||
        fail "reset-all cannot write parent directory $reset_preflight_parent"
}

reset_directory_is_empty() {
    for reset_entry in "$1"/* "$1"/.[!.]* "$1"/..?*; do
        reset_path_exists "$reset_entry" || continue
        return 1
    done
    return 0
}

preflight_reset_legacy_lock() {
    reset_legacy_lock=$1
    reset_path_exists "$reset_legacy_lock" || return 0
    test -d "$reset_legacy_lock" && test ! -L "$reset_legacy_lock" ||
        fail "$reset_legacy_lock is not an empty directory"
    test -r "$reset_legacy_lock" && test -x "$reset_legacy_lock" ||
        fail "$reset_legacy_lock is not readable and searchable"
    reset_directory_is_empty "$reset_legacy_lock" ||
        fail "$reset_legacy_lock is not an empty directory"
    preflight_reset_parent "$reset_legacy_lock"
}

preflight_reset_lease() {
    reset_path_exists "$LEASE_DIR" || return 0
    test -d "$LEASE_DIR" && test ! -L "$LEASE_DIR" ||
        fail "$LEASE_DIR is not a removable maintenance lease directory"
    test -r "$LEASE_DIR" && test -x "$LEASE_DIR" ||
        fail "$LEASE_DIR is not readable and searchable"
    test -w "$LEASE_DIR" ||
        fail "$LEASE_DIR is not removable"
    preflight_reset_parent "$LEASE_DIR"
    for reset_lease_entry in \
        "$LEASE_DIR"/* "$LEASE_DIR"/.[!.]* "$LEASE_DIR"/..?*; do
        reset_path_exists "$reset_lease_entry" || continue
        case "$(basename "$reset_lease_entry")" in
            reason | token | revision) ;;
            *) fail "$LEASE_DIR contains unexpected state" ;;
        esac
        test -f "$reset_lease_entry" || test -L "$reset_lease_entry" ||
            fail "$reset_lease_entry is not removable lease state"
    done
}

preflight_reset_all() {
    preflight_reset_parent "$MAINTENANCE_METRICS"
    if reset_path_exists "$MAINTENANCE_METRICS"; then
        test -f "$MAINTENANCE_METRICS" &&
            test ! -L "$MAINTENANCE_METRICS" &&
            test -r "$MAINTENANCE_METRICS" ||
            fail "$MAINTENANCE_METRICS is not resettable metrics state"
    fi
    if reset_path_exists "$MAINTENANCE_FLAG_FILE"; then
        test ! -d "$MAINTENANCE_FLAG_FILE" ||
            fail "$MAINTENANCE_FLAG_FILE is not a resettable maintenance flag"
        preflight_reset_parent "$MAINTENANCE_FLAG_FILE"
    fi
    preflight_reset_lease
    preflight_reset_legacy_lock "$DEPLOY_LOCK_DIR"
    preflight_reset_legacy_lock "$POSTGRES_RESTORE_LOCK_DIR"
}

reset_state_word() {
    if reset_path_exists "$1"; then
        printf present
    else
        printf absent
    fi
}

show_reset_state() {
    reset_state_label=$1
    if [ "$reset_state_label" = after ]; then
        # TEST_RESET_ON_FINAL_SUMMARY_WRITE
        :
    fi
    printf 'maintenance_reset_%s flag=%s lease=%s metrics=%s deploy_lock=%s postgres_restore_lock=%s\n' \
        "$reset_state_label" \
        "$(reset_state_word "$MAINTENANCE_FLAG_FILE")" \
        "$(reset_state_word "$LEASE_DIR")" \
        "$(reset_state_word "$MAINTENANCE_METRICS")" \
        "$(reset_state_word "$DEPLOY_LOCK_DIR")" \
        "$(reset_state_word "$POSTGRES_RESTORE_LOCK_DIR")"
}

quarantine_reset_path() {
    RESET_INFLIGHT_QUARANTINE_TARGET=$1
    reset_quarantine_label=$2
    RESET_INFLIGHT_QUARANTINE_KIND=$3
    reset_quarantine_slot=$4
    reset_quarantine_parent=$(dirname "$RESET_INFLIGHT_QUARANTINE_TARGET")
    while :; do
        reset_quarantine_random=$(openssl rand -hex 16)
        RESET_INFLIGHT_QUARANTINE_PATH="${reset_quarantine_parent}/.${reset_quarantine_label}.reset.rollback.${reset_quarantine_random}"
        # TEST_RESET_BEFORE_QUARANTINE_PLACEHOLDER_CREATE
        if mkdir "$RESET_INFLIGHT_QUARANTINE_PATH" 2>/dev/null; then
            break
        fi
        reset_path_exists "$RESET_INFLIGHT_QUARANTINE_PATH" || return 1
    done
    # TEST_RESET_AFTER_QUARANTINE_PLACEHOLDER_CREATE
    rmdir "$RESET_INFLIGHT_QUARANTINE_PATH"
    # TEST_RESET_AFTER_QUARANTINE_PLACEHOLDER_REMOVE
    mv "$RESET_INFLIGHT_QUARANTINE_TARGET" "$RESET_INFLIGHT_QUARANTINE_PATH"
    # TEST_RESET_AFTER_QUARANTINE_MV
    case "$reset_quarantine_slot" in
        metrics) RESET_METRICS_BACKUP=$RESET_INFLIGHT_QUARANTINE_PATH ;;
        flag) RESET_FLAG_QUARANTINE=$RESET_INFLIGHT_QUARANTINE_PATH ;;
        lease) RESET_LEASE_QUARANTINE=$RESET_INFLIGHT_QUARANTINE_PATH ;;
        deploy_lock)
            RESET_DEPLOY_LOCK_QUARANTINE=$RESET_INFLIGHT_QUARANTINE_PATH
            ;;
        postgres_lock)
            RESET_POSTGRES_LOCK_QUARANTINE=$RESET_INFLIGHT_QUARANTINE_PATH
            ;;
        *) return 64 ;;
    esac
    RESET_INFLIGHT_QUARANTINE_PATH=
    RESET_INFLIGHT_QUARANTINE_TARGET=
    RESET_INFLIGHT_QUARANTINE_KIND=
}

cleanup_committed_reset() {
    if [ -n "$RESET_FLAG_QUARANTINE" ]; then
        rm -f "$RESET_FLAG_QUARANTINE" || return 1
        RESET_FLAG_QUARANTINE=
        # TEST_RESET_AFTER_BACKUP_DELETE
    fi
    if [ -n "$RESET_LEASE_QUARANTINE" ]; then
        rm -f \
            "$RESET_LEASE_QUARANTINE/reason" \
            "$RESET_LEASE_QUARANTINE/token" \
            "$RESET_LEASE_QUARANTINE/revision" || return 1
        if reset_path_exists "$RESET_LEASE_QUARANTINE"; then
            rmdir "$RESET_LEASE_QUARANTINE" || return 1
        fi
        # TEST_RESET_AFTER_DIRECTORY_BACKUP_RMDIR
        RESET_LEASE_QUARANTINE=
        # TEST_RESET_AFTER_BACKUP_DELETE
    fi
    if [ -n "$RESET_DEPLOY_LOCK_QUARANTINE" ]; then
        if reset_path_exists "$RESET_DEPLOY_LOCK_QUARANTINE"; then
            rmdir "$RESET_DEPLOY_LOCK_QUARANTINE" || return 1
        fi
        # TEST_RESET_AFTER_DIRECTORY_BACKUP_RMDIR
        RESET_DEPLOY_LOCK_QUARANTINE=
        # TEST_RESET_AFTER_BACKUP_DELETE
    fi
    if [ -n "$RESET_POSTGRES_LOCK_QUARANTINE" ]; then
        if reset_path_exists "$RESET_POSTGRES_LOCK_QUARANTINE"; then
            rmdir "$RESET_POSTGRES_LOCK_QUARANTINE" || return 1
        fi
        # TEST_RESET_AFTER_DIRECTORY_BACKUP_RMDIR
        RESET_POSTGRES_LOCK_QUARANTINE=
        # TEST_RESET_AFTER_BACKUP_DELETE
    fi
    if [ -n "$RESET_METRICS_BACKUP" ]; then
        rm -f "$RESET_METRICS_BACKUP" || return 1
        RESET_METRICS_BACKUP=
        # TEST_RESET_AFTER_BACKUP_DELETE
    fi
}

reset_all_maintenance() {
    preflight_reset_all
    show_reset_state before

    TRANSACTION=reset
    install_transaction_trap
    if [ ! -d "$TEXTFILE_DIR" ]; then
        RESET_CREATED_TEXTFILE_DIR=true
    fi
    if [ ! -d "$RESET_RUNTIME_DIR" ]; then
        RESET_CREATED_RUNTIME_DIR=true
    fi
    mkdir -p "$TEXTFILE_DIR"
    if [ "$RESET_CREATED_RUNTIME_DIR" = "true" ]; then
        chgrp "$DEPLOY_GROUP" "$RESET_RUNTIME_DIR"
        chmod 0770 "$RESET_RUNTIME_DIR"
    fi
    if [ "$RESET_CREATED_TEXTFILE_DIR" = "true" ]; then
        chgrp "$DEPLOY_GROUP" "$TEXTFILE_DIR"
        chmod 0775 "$TEXTFILE_DIR"
    fi
    now=$(date -u +%s)
    stage_maintenance_metrics 0 reset "$now" "$now" "$SOURCE_REVISION"

    if reset_path_exists "$MAINTENANCE_METRICS"; then
        quarantine_reset_path \
            "$MAINTENANCE_METRICS" forge_maintenance file metrics
    fi
    if reset_path_exists "$MAINTENANCE_FLAG_FILE"; then
        quarantine_reset_path "$MAINTENANCE_FLAG_FILE" maintenance file flag
    fi
    if reset_path_exists "$LEASE_DIR"; then
        quarantine_reset_path "$LEASE_DIR" maintenance.lease directory lease
    fi
    if reset_path_exists "$DEPLOY_LOCK_DIR"; then
        quarantine_reset_path \
            "$DEPLOY_LOCK_DIR" deploy.lock directory deploy_lock
    fi
    if reset_path_exists "$POSTGRES_RESTORE_LOCK_DIR"; then
        quarantine_reset_path \
            "$POSTGRES_RESTORE_LOCK_DIR" postgres-restore.lock directory postgres_lock
    fi
    # TEST_RESET_AFTER_QUARANTINE

    RESET_METRICS_TRANSITION_ATTEMPTED=true
    # TEST_RESET_BEFORE_METRICS_MV
    mv -f "$METRICS_TMP" "$MAINTENANCE_METRICS"
    METRICS_TMP=
    # TEST_RESET_AFTER_METRICS_PUBLICATION
    TRANSACTION_COMMITTED=true
    # TEST_RESET_AFTER_COMMIT
    cleanup_committed_reset
    show_reset_state after
}

render_finish_command() {
    reason=$1
    token=$2
    load_active_lease
    test "$reason" = "$ACTIVE_REASON" || fail "reason does not match active lease"
    test "$token" = "$ACTIVE_TOKEN" || fail "token does not match active lease"

    printf 'ENV_FILE='
    shell_quote "$ENV_FILE"
    printf ' '
    shell_quote "$DEPLOY_DIR/scripts/maintenance.sh"
    printf ' finish '
    shell_quote "$reason"
    printf ' '
    shell_quote "$token"
    printf '\n'
}

publish_deploy() {
    now=$(date -u +%s)

    mkdir -p "$TEXTFILE_DIR"
    METRICS_TMP=$(mktemp "$TEXTFILE_DIR/.forge_deployment.prom.XXXXXX")
    trap cleanup_temporary_files EXIT
    install_signal_exit_traps
    printf 'forge_deployment_timestamp_seconds{revision="%s"} %s\n' \
        "$SOURCE_REVISION" "$now" > "$METRICS_TMP"
    chgrp "$DEPLOY_GROUP" "$METRICS_TMP"
    chmod 0644 "$METRICS_TMP"
    mv -f "$METRICS_TMP" "$DEPLOYMENT_METRICS"
    METRICS_TMP=
}

show_status() {
    test ! -r "$MAINTENANCE_METRICS" || cat "$MAINTENANCE_METRICS"
    test ! -r "$DEPLOYMENT_METRICS" || cat "$DEPLOYMENT_METRICS"
    if [ -d "$LEASE_DIR" ]; then
        printf 'maintenance_lease_path %s\n' "$LEASE_DIR"
        if [ -r "$LEASE_DIR/reason" ]; then
            printf 'maintenance_lease_reason '
            cat "$LEASE_DIR/reason"
        fi
        if [ -r "$LEASE_DIR/token" ]; then
            printf 'maintenance_lease_token '
            cat "$LEASE_DIR/token"
        fi
    fi
    show_operation_lock
}

release_operation_lock_on_exit() {
    status=$?
    trap '' EXIT HUP INT TERM
    release_operation_lock || true
    exit "$status"
}

run_with_operation_lock() {
    operation=$1
    shift
    if [ -n "${OPERATION_LOCK_TOKEN:-}" ]; then
        use_inherited_operation_lock || fail "cannot use inherited operation lock"
    else
        acquire_operation_lock "$operation" || fail "cannot acquire operation lock"
    fi
    trap release_operation_lock_on_exit EXIT
    install_signal_exit_traps
    # TEST_MAINTENANCE_LOCK_ACQUIRED
    "$@"
    # TEST_MAINTENANCE_COMMAND_COMPLETED
    if [ "${TRANSACTION_COMMITTED:-false}" = "true" ]; then
        return
    fi
    release_operation_lock || fail "cannot release operation lock"
    trap - EXIT HUP INT TERM
}

DATA_ROOT=${DATA_ROOT:?DATA_ROOT is required}
DEPLOY_GROUP=${DEPLOY_GROUP:-}
SOURCE_REVISION=${SOURCE_REVISION:-unknown}
MAINTENANCE_FLAG_FILE=${MAINTENANCE_FLAG_FILE:-"$DATA_ROOT/runtime/maintenance"}
TEXTFILE_DIR="$DATA_ROOT/runtime/node-exporter"
RESET_RUNTIME_DIR=$(dirname "$TEXTFILE_DIR")
MAINTENANCE_METRICS="$TEXTFILE_DIR/forge_maintenance.prom"
DEPLOYMENT_METRICS="$TEXTFILE_DIR/forge_deployment.prom"
LEASE_DIR="$DATA_ROOT/runtime/maintenance.lease"
DEPLOY_LOCK_DIR="$DATA_ROOT/run/deploy.lock"
POSTGRES_RESTORE_LOCK_DIR="$DATA_ROOT/run/postgres-restore.lock"
METRICS_TMP=
FLAG_TMP=
METRICS_BACKUP=
FLAG_BACKUP=
LEASE_TMP=
REVISION_TMP=
REVISION_BACKUP=
PREVIOUS_METRICS=false
METRICS_TRANSITION_ATTEMPTED=false
FLAG_TRANSITION_ATTEMPTED=false
REVISION_TRANSITION_ATTEMPTED=false
ACQUIRED_LEASE=false
TRANSACTION=
TRANSACTION_COMMITTED=false
ACTIVE_REASON=
ACTIVE_TOKEN=
ACTIVE_REVISION=
RESET_INFLIGHT_QUARANTINE_PATH=
RESET_INFLIGHT_QUARANTINE_TARGET=
RESET_INFLIGHT_QUARANTINE_KIND=
RESET_METRICS_BACKUP=
RESET_FLAG_QUARANTINE=
RESET_LEASE_QUARANTINE=
RESET_DEPLOY_LOCK_QUARANTINE=
RESET_POSTGRES_LOCK_QUARANTINE=
RESET_METRICS_TRANSITION_ATTEMPTED=false
RESET_CREATED_TEXTFILE_DIR=false
RESET_CREATED_RUNTIME_DIR=false
command=${1:-status}

case "$command" in
    start)
        test "$#" -eq 3 || fail "start requires REASON and DURATION_SECONDS"
        validate_reason "$2"
        validate_duration "$3"
        validate_revision
        validate_deploy_group
        umask 0007
        run_with_operation_lock "$2" start_maintenance "$2" "$3"
        ;;
    finish)
        test "$#" -eq 3 || fail "finish requires REASON and TOKEN"
        validate_reason "$2"
        validate_token "$3"
        validate_revision
        validate_deploy_group
        umask 0007
        run_with_operation_lock "$2" finish_maintenance "$2" "$3"
        ;;
    finish-command)
        test "$#" -eq 3 || fail "finish-command requires REASON and TOKEN"
        validate_reason "$2"
        validate_token "$3"
        validate_revision
        render_finish_command "$2" "$3"
        ;;
    publish-deploy)
        test "$#" -eq 1 || fail "publish-deploy does not accept arguments"
        validate_revision
        validate_deploy_group
        umask 0007
        publish_deploy
        ;;
    reset-all)
        test "$#" -eq 1 || fail "reset-all does not accept arguments"
        test "${CONFIRM_RESET_ALL_LEASES:-false}" = true ||
            fail "reset-all requires CONFIRM_RESET_ALL_LEASES=true"
        validate_revision
        validate_deploy_group
        umask 0007
        run_with_operation_lock reset reset_all_maintenance
        ;;
    status)
        test "$#" -le 1 || fail "status does not accept arguments"
        show_status
        ;;
    *)
        usage
        exit 2
        ;;
esac
