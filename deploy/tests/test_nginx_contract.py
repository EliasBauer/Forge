from __future__ import annotations

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
TEMPLATE = (DEPLOY / "nginx/nginx.conf.template").read_text()
ENTRYPOINT = (DEPLOY / "nginx/entrypoint.sh").read_text()


def _block(text: str, marker: str) -> str:
    start = text.index(marker)
    opening = text.index("{", start)
    depth = 0
    for position in range(opening, len(text)):
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                return text[start : position + 1]
    raise AssertionError(f"unclosed nginx block: {marker}")


def _server_blocks() -> list[str]:
    blocks = []
    position = 0
    while (start := TEMPLATE.find("server {", position)) != -1:
        block = _block(TEMPLATE[start:], "server {")
        blocks.append(block)
        position = start + len(block)
    return blocks


def test_nginx_exposes_exactly_the_three_virtual_hosts() -> None:
    assert "server_name ${APP_DOMAIN};" in TEMPLATE
    assert "server_name ${MONITORING_DOMAIN};" in TEMPLATE
    assert "server_name ${ADMIN_DOMAIN};" in TEMPLATE
    assert TEMPLATE.count("listen 443 ssl") == 3
    assert "proxy_pass http://forge_web;" in TEMPLATE
    assert "set $grafana_backend http://grafana:3000;" in TEMPLATE
    assert "set $pgadmin_backend http://pgadmin:5050;" in TEMPLATE
    assert "upstream grafana_backend" not in TEMPLATE
    assert "upstream pgadmin_backend" not in TEMPLATE


def test_nginx_redirects_configured_http_hosts_and_rejects_others() -> None:
    redirect = next(block for block in _server_blocks() if "return 308" in block)
    assert "server_name ${APP_DOMAIN} ${MONITORING_DOMAIN} ${ADMIN_DOMAIN};" in redirect
    assert "return 308 https://$host$request_uri;" in redirect
    fallback = next(
        block for block in _server_blocks() if "listen 80 default_server" in block
    )
    assert "return 404;" in fallback


def test_nginx_redacts_query_strings_from_access_logs() -> None:
    assert '"$request_method $uri $server_protocol"' in TEMPLATE
    assert (
        "$request_uri" not in TEMPLATE.split("log_format safe", 1)[1].split(";", 1)[0]
    )


def test_nginx_proxies_graphql_subscriptions_and_app_routes_only() -> None:
    api = _block(TEMPLATE, "location ~ ^/(graphql|api|admin|health)(/|$)")
    assert "proxy_http_version 1.1;" in api
    assert "proxy_set_header Upgrade $http_upgrade;" in api
    assert "proxy_set_header Connection $connection_upgrade;" in api
    assert "proxy_set_header X-Forwarded-Proto https;" in api
    assert "proxy_read_timeout 300s;" in api
    assert "metrics" not in TEMPLATE.split("upstream forge_web", 1)[1]


def test_nginx_serves_spa_static_and_revalidates_entry_document() -> None:
    assert "root /usr/share/nginx/html;" in TEMPLATE
    assert "location /static/ {\n        alias /static/;" in TEMPLATE
    assert "try_files $uri $uri/ /index.html;" in TEMPLATE
    entry = _block(TEMPLATE, "location = /index.html")
    assert 'add_header Cache-Control "no-cache, must-revalidate" always;' in entry


def test_nginx_blocks_every_public_app_location_during_maintenance() -> None:
    assert "if (-f /run/forge/maintenance) {" in TEMPLATE
    assert "error_page 503 /maintenance.html;" in TEMPLATE
    guard = _block(TEMPLATE, 'map "$maintenance_mode:$status:$uri" $serve_maintenance')
    assert "~^1:[^:]*:/nginx-healthz$ 0;" in guard
    assert "~^1:503:/maintenance\\.html$ 0;" in guard
    assert "~^1:[^:]*:/logo\\.svg$ 0;" in guard
    assert "~^1: 1;" in guard
    exemptions = re.findall(r"~\^1:[^ ]+ 0;", guard)
    assert len(exemptions) == 3


def test_nginx_maintenance_page_is_self_contained_and_branded() -> None:
    page = (DEPLOY / "nginx/maintenance.html").read_text()
    assert '<html lang="de">' in page
    assert 'src="/logo.svg"' in page
    assert "http://" not in page and "https://" not in page
    assert "mailto:" not in page
    dockerfile = (DEPLOY / "nginx/Dockerfile").read_text()
    assert "deploy/nginx/maintenance.html" in dockerfile


def test_nginx_upstream_avoids_unsupported_resolve_parameter() -> None:
    upstream = _block(TEMPLATE, "upstream forge_web")
    assert "server web:8000;" in upstream
    assert "zone forge_web 256k;" in upstream
    assert "resolve" not in upstream


def test_nginx_enables_http2_on_every_tls_virtual_host() -> None:
    tls_blocks = [block for block in _server_blocks() if "listen 443 ssl" in block]
    assert len(tls_blocks) == 3
    for block in tls_blocks:
        assert "http2 on;" in block
        assert "ssl_protocols TLSv1.2 TLSv1.3;" in block
        assert "Strict-Transport-Security" not in block


def test_nginx_admin_host_requires_basic_auth() -> None:
    admin = next(
        block for block in _server_blocks() if "server_name ${ADMIN_DOMAIN};" in block
    )
    assert 'auth_basic "Forge administration";' in admin
    assert "auth_basic_user_file ${ADMIN_HTPASSWD_FILE};" in admin


def test_nginx_exposes_stub_status_for_the_exporter_only_internally() -> None:
    status = next(block for block in _server_blocks() if "listen 8080" in block)
    assert "stub_status;" in status
    assert "location = /nginx_status" in status


def test_nginx_entrypoint_validates_inputs_renders_and_tests_config() -> None:
    required = (
        "for variable in TLS_CERT_FILE TLS_KEY_FILE ADMIN_HTPASSWD_FILE "
        "APP_DOMAIN MONITORING_DOMAIN ADMIN_DOMAIN"
    )
    assert required in ENTRYPOINT
    assert 'openssl x509 -in "$TLS_CERT_FILE" -noout -checkend 0' in ENTRYPOINT
    assert "install -o www-data -g www-data -m 0400" in ENTRYPOINT
    rendered_variables = (
        "envsubst '${APP_DOMAIN} ${MONITORING_DOMAIN} ${ADMIN_DOMAIN} "
        "${TLS_CERT_FILE} ${TLS_KEY_FILE} ${ADMIN_HTPASSWD_FILE}'"
    )
    assert rendered_variables in ENTRYPOINT
    assert "/etc/nginx/templates/forge.conf.template" in ENTRYPOINT
    assert "nginx -t" in ENTRYPOINT
    assert ENTRYPOINT.rstrip().endswith('exec nginx -g "daemon off;"')
