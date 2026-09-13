#!/bin/sh
# Resolve the configured deployment group to the numeric GID used by file-backed
# Compose secrets. This is intentionally internal; operators configure only
# DEPLOY_GROUP.
resolve_deploy_group() {
    deploy_group=${DEPLOY_GROUP:-}
    case "$deploy_group" in
        "" | *[!A-Za-z0-9_.-]*)
            echo "DEPLOY_GROUP must be a safe group name" >&2
            return 1
            ;;
    esac

    group_record=$(getent group "$deploy_group" 2>/dev/null) || {
        echo "DEPLOY_GROUP does not exist" >&2
        return 1
    }
    deploy_group_gid=$(printf '%s\n' "$group_record" | awk -F: -v group="$deploy_group" '
        NF != 4 || $1 != group || $3 !~ /^[0-9]+$/ { invalid=1; next }
        { count++; gid=$3 }
        END {
            if (invalid || count != 1) {
                exit 1
            }
            print gid
        }
    ') || {
        echo "DEPLOY_GROUP must resolve to exactly one numeric GID" >&2
        return 1
    }

    DEPLOY_GROUP_GID=$deploy_group_gid
    export DEPLOY_GROUP_GID
}

# Prefer the Docker Compose v2 plugin, with the standalone v2 binary as a
# compatibility fallback for production hosts.
compose() {
    resolve_deploy_group || return

    if docker compose version >/dev/null 2>&1; then
        docker compose "$@"
        return
    fi

    if command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
        docker-compose "$@"
        return
    fi

    echo "docker compose or docker-compose is required" >&2
    return 1
}
