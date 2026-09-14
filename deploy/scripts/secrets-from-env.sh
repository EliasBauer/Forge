#!/bin/sh
set -eu

# ----------------------------------------------------------------------------
# Write the per-secret files Compose mounts from one operator-maintained
# env-style file. Re-run after changing a value there (e.g. a new Bexio
# token), then recreate the containers that read it.
#
# Usage:
#   ./scripts/secrets-from-env.sh [SOURCE]   default: $SECRETS_DIR/forge-secrets.env
#
# SOURCE keys (KEY=value, one per line, no quotes):
#   ADMIN_BASIC_AUTH_PASSWORD  -> admin_htpasswd.txt (hashed, user "admin")
#   GRAFANA_ADMIN_PASSWORD     -> grafana_admin_password.txt
#   PGADMIN_PASSWORD           -> pgadmin_password.txt
#   BEXIO_ACCESS_TOKEN         -> bexio_access_token.txt (may be empty: dev mode)
#
# django_secret_key, postgres_password and meilisearch_api_key are generated
# randomly on first run and never overwritten; teams_workflow_url and
# smtp_password are created empty if missing. SECRETS_DIR and DEPLOY_GROUP
# come from ENV_FILE (default <deploy>/.env).
# ----------------------------------------------------------------------------

DEPLOY_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
ENV_FILE=${ENV_FILE:-"$DEPLOY_DIR/.env"}
if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi
SECRETS_DIR=${SECRETS_DIR:-./secrets}
case "$SECRETS_DIR" in
    /*) ;;
    *) SECRETS_DIR=$DEPLOY_DIR/$SECRETS_DIR ;;
esac
SOURCE=${1:-"$SECRETS_DIR/forge-secrets.env"}
DEPLOY_GROUP=${DEPLOY_GROUP:?DEPLOY_GROUP is required}

fail() {
    echo "secrets-from-env failed: $*" >&2
    exit 1
}

test -d "$SECRETS_DIR" || fail "SECRETS_DIR does not exist: $SECRETS_DIR"
test -w "$SECRETS_DIR" || fail "SECRETS_DIR is not writable: $SECRETS_DIR"
test -r "$SOURCE" || fail "source file is not readable: $SOURCE"

# First value of KEY= in SOURCE; never echoed.
value() {
    sed -n "s/^$1=//p" "$SOURCE" | head -n 1
}

# Write a secret file atomically with the group-private mode the preflight expects.
write_secret() {
    umask 027
    printf '%s' "$2" > "$SECRETS_DIR/$1.txt.tmp"
    chgrp "$DEPLOY_GROUP" "$SECRETS_DIR/$1.txt.tmp"
    chmod 0640 "$SECRETS_DIR/$1.txt.tmp"
    mv -f "$SECRETS_DIR/$1.txt.tmp" "$SECRETS_DIR/$1.txt"
}

for key in ADMIN_BASIC_AUTH_PASSWORD GRAFANA_ADMIN_PASSWORD PGADMIN_PASSWORD; do
    test -n "$(value "$key")" || fail "$key is empty in $SOURCE"
done

htpasswd_hash=$(value ADMIN_BASIC_AUTH_PASSWORD | openssl passwd -apr1 -stdin)
write_secret admin_htpasswd "admin:$htpasswd_hash
"
write_secret grafana_admin_password "$(value GRAFANA_ADMIN_PASSWORD)"
write_secret pgadmin_password "$(value PGADMIN_PASSWORD)"
write_secret bexio_access_token "$(value BEXIO_ACCESS_TOKEN)"

for name in django_secret_key postgres_password meilisearch_api_key; do
    test -s "$SECRETS_DIR/$name.txt" || write_secret "$name" "$(openssl rand -base64 48 | tr -d '\n')"
done
for name in teams_workflow_url smtp_password; do
    test -e "$SECRETS_DIR/$name.txt" || write_secret "$name" ""
done

echo "secrets written to $SECRETS_DIR"
