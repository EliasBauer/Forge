#!/bin/sh
set -eu

# ----------------------------------------------------------------------------
# One-time host preparation for a Forge Compose host (run as root).
#
# Does the root-only steps from deploy/README.md and docs/start_prod.md:
# deploy group, data directories with the container UIDs, TLS directory with
# a self-signed certificate (only if none exists), the secrets directory,
# SSH key-only login and unattended security upgrades.
#
# Usage:
#   sudo OPERATOR=<login> APP_DOMAIN=<host> sh deploy/scripts/host-prep.sh
#
# Environment:
# - OPERATOR (required): login that runs the deploy scripts
# - APP_DOMAIN (required), MONITORING_DOMAIN, ADMIN_DOMAIN: certificate SANs;
#   defaults monitoring.<APP_DOMAIN> and db.<APP_DOMAIN>
# - DATA_ROOT, BACKUP_SHARE, SECRETS_DIR: same meaning as in deploy/.env
# Idempotent: safe to run again after changing a value.
# ----------------------------------------------------------------------------

OPERATOR=${OPERATOR:?OPERATOR (login of the deploy user) is required}
APP_DOMAIN=${APP_DOMAIN:?APP_DOMAIN is required}
MONITORING_DOMAIN=${MONITORING_DOMAIN:-monitoring.$APP_DOMAIN}
ADMIN_DOMAIN=${ADMIN_DOMAIN:-db.$APP_DOMAIN}
DATA_ROOT=${DATA_ROOT:-/srv/forge/data}
BACKUP_SHARE=${BACKUP_SHARE:-/srv/forge/backup-share}
SECRETS_DIR=${SECRETS_DIR:-/etc/forge/secrets}
TLS_DIR=/etc/forge/tls

test "$(id -u)" -eq 0 || { echo "run as root (sudo)" >&2; exit 1; }
id "$OPERATOR" >/dev/null 2>&1 || { echo "no such user: $OPERATOR" >&2; exit 1; }

# Deploy group: reads .env, secrets and the TLS key; Docker access for the operator.
groupadd --force forge-deploy
usermod -aG forge-deploy "$OPERATOR"
if getent group docker >/dev/null; then usermod -aG docker "$OPERATOR"; fi

# Data directories, owned by the UID each container runs with (preflight checks these).
for dir in postgres redis meilisearch static run runtime/node-exporter backups celerybeat \
    alertmanager prometheus grafana loki alloy pushgateway pgadmin restore-verification/files; do
    mkdir -p "$DATA_ROOT/$dir"
done
mkdir -p "$BACKUP_SHARE" "$TLS_DIR" "$SECRETS_DIR"
chown -R 1000:1000 "$DATA_ROOT/static" "$DATA_ROOT/backups" "$DATA_ROOT/celerybeat" "$DATA_ROOT/restore-verification" "$BACKUP_SHARE"
chmod 0755 "$DATA_ROOT/static"
chmod 0750 "$DATA_ROOT/backups" "$DATA_ROOT/celerybeat" "$DATA_ROOT/restore-verification" "$BACKUP_SHARE"
chown 65534:65534 "$DATA_ROOT/alertmanager" "$DATA_ROOT/prometheus" "$DATA_ROOT/pushgateway"
chmod 0750 "$DATA_ROOT/alertmanager" "$DATA_ROOT/prometheus" "$DATA_ROOT/pushgateway"
chown 472:0 "$DATA_ROOT/grafana" && chmod 0750 "$DATA_ROOT/grafana"
chown 10001:10001 "$DATA_ROOT/loki" && chmod 0750 "$DATA_ROOT/loki"
chown 5050:5050 "$DATA_ROOT/pgadmin" && chmod 0750 "$DATA_ROOT/pgadmin"
chgrp forge-deploy "$DATA_ROOT/run" "$DATA_ROOT/runtime" && chmod 2770 "$DATA_ROOT/run" "$DATA_ROOT/runtime"
chgrp forge-deploy "$DATA_ROOT/runtime/node-exporter" && chmod 2775 "$DATA_ROOT/runtime/node-exporter"

# Secrets outside the checkout; files inside get 0640 forge-deploy (see start_prod.md).
chgrp forge-deploy "$SECRETS_DIR" && chmod 0750 "$SECRETS_DIR"

# Self-signed certificate for the three host names, only when none exists.
if [ ! -f "$TLS_DIR/fullchain.pem" ]; then
    openssl req -x509 -nodes -newkey rsa:4096 -sha256 -days 3650 \
        -keyout "$TLS_DIR/privkey.pem" -out "$TLS_DIR/fullchain.pem" \
        -subj "/CN=$APP_DOMAIN" \
        -addext "subjectAltName=DNS:$APP_DOMAIN,DNS:$MONITORING_DOMAIN,DNS:$ADMIN_DOMAIN"
fi
chgrp forge-deploy "$TLS_DIR/privkey.pem" && chmod 0640 "$TLS_DIR/privkey.pem"
chmod 0644 "$TLS_DIR/fullchain.pem"

# SSH: keys only. Skipped when the operator has no key yet (would lock you out).
operator_home=$(getent passwd "$OPERATOR" | cut -d: -f6)
if [ -s "$operator_home/.ssh/authorized_keys" ]; then
    mkdir -p /etc/ssh/sshd_config.d
    printf '%s\n' 'PasswordAuthentication no' 'KbdInteractiveAuthentication no' 'PermitRootLogin no' \
        > /etc/ssh/sshd_config.d/50-forge.conf
    sshd -t && (systemctl reload ssh 2>/dev/null || systemctl reload sshd)
else
    echo "warning: $operator_home/.ssh/authorized_keys is empty, SSH password login stays enabled" >&2
fi

# Unattended security upgrades (Debian/Ubuntu).
if command -v apt-get >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q unattended-upgrades >/dev/null
    printf '%s\n' 'APT::Periodic::Update-Package-Lists "1";' 'APT::Periodic::Unattended-Upgrade "1";' \
        > /etc/apt/apt.conf.d/20auto-upgrades
    systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
fi

echo "host prep done: log out and back in so $OPERATOR picks up the new groups"
