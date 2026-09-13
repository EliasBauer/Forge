#!/bin/sh

OPERATION_LOCK_ACQUIRED=false
OPERATION_LOCK_OWNER=false
OPERATION_LOCK_TOKEN=${OPERATION_LOCK_TOKEN:-}
OPERATION_LOCK_FD=${OPERATION_LOCK_FD:-9}
OPERATION_LOCK_FILE=
OPERATION_LOCK_METADATA=

operation_lock_fail() {
    printf '%s\n' "operation lock failed: $*" >&2
    return 1
}

operation_lock_validate_safe_value() {
    operation_lock_value_name=$1
    operation_lock_value=$2
    operation_lock_value_max_length=$3

    case "$operation_lock_value" in
        "" | *[!A-Za-z0-9._-]*)
            operation_lock_fail \
                "$operation_lock_value_name must contain only A-Za-z0-9._-"
            return 1
            ;;
    esac
    if [ "${#operation_lock_value}" -gt "$operation_lock_value_max_length" ]; then
        operation_lock_fail "$operation_lock_value_name is too long"
        return 1
    fi
}

operation_lock_validate_numeric_value() {
    operation_lock_numeric_name=$1
    operation_lock_numeric_value=$2

    case "$operation_lock_numeric_value" in
        "" | *[!0-9]*)
            operation_lock_fail "$operation_lock_numeric_name must be numeric"
            return 1
            ;;
    esac
}

operation_lock_validate_operation() {
    case "$1" in
        deploy | restore | reset) ;;
        *)
            operation_lock_fail \
                "operation must be one of deploy, restore, or reset"
            return 1
            ;;
    esac
}

operation_lock_validate_configuration() {
    if [ -z "${DATA_ROOT:-}" ]; then
        operation_lock_fail "DATA_ROOT is required"
        return 1
    fi
    if [ -z "${DEPLOY_GROUP:-}" ]; then
        operation_lock_fail "DEPLOY_GROUP is required"
        return 1
    fi
    if [ -z "${SOURCE_REVISION:-}" ]; then
        operation_lock_fail "SOURCE_REVISION is required"
        return 1
    fi

    operation_lock_validate_safe_value DEPLOY_GROUP "$DEPLOY_GROUP" 128 || return 1
    operation_lock_validate_safe_value SOURCE_REVISION "$SOURCE_REVISION" 128 || return 1
    command -v flock >/dev/null 2>&1 || {
        operation_lock_fail "flock is required"
        return 1
    }

    OPERATION_LOCK_FILE=$DATA_ROOT/run/operations.lock
    OPERATION_LOCK_METADATA=$DATA_ROOT/run/operations.lock.meta
}

operation_lock_metadata_value() {
    operation_lock_requested_key=$1
    operation_lock_found_value=

    [ -f "$OPERATION_LOCK_METADATA" ] || return 1
    while IFS='=' read -r operation_lock_key operation_lock_value; do
        [ "$operation_lock_key" = "$operation_lock_requested_key" ] || continue
        operation_lock_found_value=$operation_lock_value
    done < "$OPERATION_LOCK_METADATA"

    [ -n "$operation_lock_found_value" ] || return 1
    printf '%s\n' "$operation_lock_found_value"
}

operation_lock_metadata_is_safe() {
    operation_lock_metadata_key=$1
    operation_lock_metadata_value_to_validate=$2

    case "$operation_lock_metadata_key" in
        operation_lock_operation)
            operation_lock_validate_operation "$operation_lock_metadata_value_to_validate"
            ;;
        operation_lock_uid | operation_lock_pid | operation_lock_started_at)
            operation_lock_validate_numeric_value \
                "$operation_lock_metadata_key" "$operation_lock_metadata_value_to_validate"
            ;;
        operation_lock_user | operation_lock_revision | operation_lock_token)
            operation_lock_validate_safe_value \
                "$operation_lock_metadata_key" \
                "$operation_lock_metadata_value_to_validate" 128
            ;;
        *) return 1 ;;
    esac
}

operation_lock_write_metadata() {
    operation_lock_operation=$1
    operation_lock_timestamp=$2
    operation_lock_user=$(id -un) || return 1
    operation_lock_uid=$(id -u) || return 1
    operation_lock_pid=$$
    operation_lock_random=$(openssl rand -hex 16) || return 1
    OPERATION_LOCK_TOKEN="${operation_lock_operation}-${operation_lock_timestamp}-${operation_lock_pid}-${operation_lock_random}"

    operation_lock_validate_safe_value \
        operation_lock_user "$operation_lock_user" 128 || return 1
    operation_lock_validate_numeric_value operation_lock_uid "$operation_lock_uid" || return 1
    operation_lock_validate_numeric_value operation_lock_pid "$operation_lock_pid" || return 1
    operation_lock_validate_numeric_value operation_lock_started_at \
        "$operation_lock_timestamp" || return 1
    operation_lock_validate_safe_value operation_lock_token "$OPERATION_LOCK_TOKEN" 128 || return 1

    operation_lock_metadata_tmp=$(mktemp "$DATA_ROOT/run/.operations.lock.meta.XXXXXX") ||
        return 1
    chmod 0660 "$operation_lock_metadata_tmp" || {
        rm -f "$operation_lock_metadata_tmp"
        return 1
    }
    chgrp "$DEPLOY_GROUP" "$operation_lock_metadata_tmp" || {
        rm -f "$operation_lock_metadata_tmp"
        return 1
    }
    {
        printf 'operation_lock_operation=%s\n' "$operation_lock_operation"
        printf 'operation_lock_user=%s\n' "$operation_lock_user"
        printf 'operation_lock_uid=%s\n' "$operation_lock_uid"
        printf 'operation_lock_pid=%s\n' "$operation_lock_pid"
        printf 'operation_lock_started_at=%s\n' "$operation_lock_timestamp"
        printf 'operation_lock_revision=%s\n' "$SOURCE_REVISION"
        printf 'operation_lock_token=%s\n' "$OPERATION_LOCK_TOKEN"
    } > "$operation_lock_metadata_tmp" || {
        rm -f "$operation_lock_metadata_tmp"
        return 1
    }
    mv "$operation_lock_metadata_tmp" "$OPERATION_LOCK_METADATA" || {
        rm -f "$operation_lock_metadata_tmp"
        return 1
    }
}

acquire_operation_lock() {
    operation_lock_requested_operation=${1:-}
    OPERATION_LOCK_ACQUIRED=false
    OPERATION_LOCK_OWNER=false
    OPERATION_LOCK_TOKEN=
    operation_lock_validate_operation "$operation_lock_requested_operation" || return 1
    operation_lock_validate_configuration || return 1
    umask 0007

    mkdir -p "$DATA_ROOT" || {
        operation_lock_fail "cannot create $DATA_ROOT"
        return 1
    }
    operation_lock_created_run=false
    if [ ! -d "$DATA_ROOT/run" ]; then
        if mkdir "$DATA_ROOT/run" 2>/dev/null; then
            operation_lock_created_run=true
        elif [ ! -d "$DATA_ROOT/run" ]; then
            operation_lock_fail "cannot create $DATA_ROOT/run"
            return 1
        fi
    fi
    if [ "$operation_lock_created_run" = true ]; then
        chgrp "$DEPLOY_GROUP" "$DATA_ROOT/run" || {
            operation_lock_fail \
                "cannot assign $DATA_ROOT/run to DEPLOY_GROUP $DEPLOY_GROUP"
            return 1
        }
        chmod 2770 "$DATA_ROOT/run" || {
            operation_lock_fail "cannot set shared mode on $DATA_ROOT/run"
            return 1
        }
    fi
    exec 9>>"$OPERATION_LOCK_FILE" || {
        operation_lock_fail "cannot open $OPERATION_LOCK_FILE"
        return 1
    }
    if ! flock -n 9; then
        printf '%s\n' "operation lock is held" >&2
        show_operation_lock >&2 || true
        exec 9>&-
        return 1
    fi
    operation_lock_file_metadata=$(stat -c '%G %a' "$OPERATION_LOCK_FILE" 2>/dev/null) || {
        operation_lock_failure_status=$?
        operation_lock_fail "cannot inspect $OPERATION_LOCK_FILE"
        flock -u 9 || true
        exec 9>&-
        return "$operation_lock_failure_status"
    }
    set -- $operation_lock_file_metadata
    operation_lock_file_group=$1
    operation_lock_file_mode=$2
    if [ "$operation_lock_file_group" != "$DEPLOY_GROUP" ]; then
        chgrp "$DEPLOY_GROUP" "$OPERATION_LOCK_FILE" || {
            operation_lock_failure_status=$?
            operation_lock_fail \
                "cannot assign $OPERATION_LOCK_FILE to DEPLOY_GROUP $DEPLOY_GROUP"
            flock -u 9 || true
            exec 9>&-
            return "$operation_lock_failure_status"
        }
    fi
    if [ "$operation_lock_file_mode" != 660 ]; then
        chmod 0660 "$OPERATION_LOCK_FILE" || {
            operation_lock_failure_status=$?
            operation_lock_fail "cannot set shared mode on $OPERATION_LOCK_FILE"
            flock -u 9 || true
            exec 9>&-
            return "$operation_lock_failure_status"
        }
    fi

    operation_lock_now=$(date -u +%s) || {
        flock -u 9 || true
        exec 9>&-
        return 1
    }
    operation_lock_write_metadata "$operation_lock_requested_operation" "$operation_lock_now" || {
        OPERATION_LOCK_TOKEN=
        flock -u 9 || true
        exec 9>&-
        return 1
    }

    OPERATION_LOCK_ACQUIRED=true
    OPERATION_LOCK_OWNER=true
    export OPERATION_LOCK_FD OPERATION_LOCK_TOKEN
}

use_inherited_operation_lock() {
    operation_lock_validate_configuration || return 1
    [ "$OPERATION_LOCK_FD" = 9 ] || {
        operation_lock_fail "inherited operation lock fd must be 9"
        return 1
    }
    [ -e "/dev/fd/$OPERATION_LOCK_FD" ] || {
        operation_lock_fail "inherited operation lock fd is unavailable"
        return 1
    }
    [ "/dev/fd/$OPERATION_LOCK_FD" -ef "$OPERATION_LOCK_FILE" ] || {
        operation_lock_fail "inherited operation lock fd is not operations.lock"
        return 1
    }
    flock -n "$OPERATION_LOCK_FD" || {
        operation_lock_fail "inherited operation lock is not held"
        return 1
    }
    operation_lock_validate_safe_value operation_lock_token \
        "$OPERATION_LOCK_TOKEN" 128 || return 1
    operation_lock_metadata_token=$(operation_lock_metadata_value operation_lock_token) || {
        operation_lock_fail "inherited operation lock metadata is unavailable"
        return 1
    }
    operation_lock_metadata_is_safe operation_lock_token "$operation_lock_metadata_token" || {
        operation_lock_fail "inherited operation lock metadata is invalid"
        return 1
    }
    [ "$OPERATION_LOCK_TOKEN" = "$operation_lock_metadata_token" ] || {
        operation_lock_fail "inherited operation lock token does not match metadata"
        return 1
    }

    OPERATION_LOCK_ACQUIRED=true
    OPERATION_LOCK_OWNER=false
    export OPERATION_LOCK_FD OPERATION_LOCK_TOKEN
}

release_operation_lock() {
    if [ "$OPERATION_LOCK_ACQUIRED" != true ] || [ "$OPERATION_LOCK_OWNER" != true ]; then
        return 0
    fi

    if [ -f "$OPERATION_LOCK_METADATA" ]; then
        operation_lock_metadata_token=$(operation_lock_metadata_value operation_lock_token) ||
            operation_lock_metadata_token=
        if [ -n "$operation_lock_metadata_token" ] &&
            operation_lock_metadata_is_safe operation_lock_token "$operation_lock_metadata_token" &&
            [ "$operation_lock_metadata_token" = "$OPERATION_LOCK_TOKEN" ]; then
            if ! rm -f "$OPERATION_LOCK_METADATA"; then
                printf '%s\n' "operation lock cleanup failed: could not remove owner metadata" >&2
            fi
        fi
    fi
    if ! flock -u 9; then
        printf '%s\n' "operation lock cleanup failed: could not unlock fd 9" >&2
    fi
    if ! exec 9>&-; then
        printf '%s\n' "operation lock cleanup failed: could not close fd 9" >&2
    fi
    OPERATION_LOCK_ACQUIRED=false
    OPERATION_LOCK_OWNER=false
    OPERATION_LOCK_TOKEN=
    export OPERATION_LOCK_FD OPERATION_LOCK_TOKEN
}

show_operation_lock() {
    [ -n "$OPERATION_LOCK_METADATA" ] || {
        [ -n "${DATA_ROOT:-}" ] || return 0
        OPERATION_LOCK_METADATA=$DATA_ROOT/run/operations.lock.meta
    }
    [ -f "$OPERATION_LOCK_METADATA" ] || return 0

    while IFS='=' read -r operation_lock_key operation_lock_value; do
        case "$operation_lock_key" in
            operation_lock_operation | operation_lock_user | operation_lock_uid | \
                operation_lock_pid | operation_lock_started_at | operation_lock_revision)
                operation_lock_metadata_is_safe \
                    "$operation_lock_key" "$operation_lock_value" || continue
                printf '%s=%s\n' "$operation_lock_key" "$operation_lock_value"
                ;;
        esac
    done < "$OPERATION_LOCK_METADATA"
}
