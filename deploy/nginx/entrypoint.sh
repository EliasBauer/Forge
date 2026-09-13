#!/bin/sh
set -eu

for variable in TLS_CERT_FILE TLS_KEY_FILE ADMIN_HTPASSWD_FILE APP_DOMAIN MONITORING_DOMAIN ADMIN_DOMAIN; do
  eval "value=\${$variable:-}"
  test -n "$value" || {
    echo "$variable must be configured" >&2
    exit 1
  }
done
for variable in TLS_CERT_FILE TLS_KEY_FILE ADMIN_HTPASSWD_FILE; do
  eval "file=\${$variable:-}"
  test -r "$file" || {
    echo "$variable must reference a readable file" >&2
    exit 1
  }
done

install -d -o root -g root -m 0755 /run/nginx
install -o www-data -g www-data -m 0400 "$ADMIN_HTPASSWD_FILE" /run/nginx/admin_htpasswd
ADMIN_HTPASSWD_FILE=/run/nginx/admin_htpasswd
export ADMIN_HTPASSWD_FILE

openssl x509 -in "$TLS_CERT_FILE" -noout -checkend 0
envsubst '${APP_DOMAIN} ${MONITORING_DOMAIN} ${ADMIN_DOMAIN} ${TLS_CERT_FILE} ${TLS_KEY_FILE} ${ADMIN_HTPASSWD_FILE}' \
  < /etc/nginx/templates/forge.conf.template \
  > /etc/nginx/conf.d/default.conf
nginx -t
exec nginx -g "daemon off;"
