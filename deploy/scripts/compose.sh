#!/bin/sh
set -eu

# Run Docker Compose with the same deployment-group resolution used by the
# operational scripts. Operators configure DEPLOY_GROUP in ENV_FILE.
DEPLOY_DIR=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd -P)
ENV_FILE=${ENV_FILE:-"$DEPLOY_DIR/.env"}

if [ ! -r "$ENV_FILE" ]; then
    echo "ENV_FILE is not readable: $ENV_FILE" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Manual runs (backups) record the checkout revision like deploy.sh does.
if [ -z "${SOURCE_REVISION:-}" ] && command -v git >/dev/null 2>&1; then
    SOURCE_REVISION=$(git -C "$DEPLOY_DIR" rev-parse --short HEAD 2>/dev/null || printf 'unknown')
    export SOURCE_REVISION
fi

# shellcheck source=lib/compose.sh
. "$DEPLOY_DIR/scripts/lib/compose.sh"

cd "$DEPLOY_DIR"
compose "$@"
