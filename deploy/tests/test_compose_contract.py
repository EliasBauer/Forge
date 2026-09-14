from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

DEPLOY = Path(__file__).resolve().parents[1]
COMPOSE: dict[str, Any] = yaml.safe_load((DEPLOY / "compose.yml").read_text())

CORE_RENDERED_SERVICES = {
    "postgres",
    "pgbouncer",
    "redis",
    "meilisearch",
    "django-migrate",
    "web",
    "celery-worker",
    "celery-beat",
    "nginx",
}
OBSERVABILITY_SERVICES = {
    "prometheus",
    "alertmanager",
    "blackbox-exporter",
    "grafana",
    "loki",
    "alloy",
    "node-exporter",
    "postgres-exporter",
    "pgbouncer-exporter",
    "redis-exporter",
    "celery-exporter",
    "nginx-exporter",
    "pushgateway",
}
PROFILE_SERVICES = {
    "deployment": {"search-index"},
    "observability": OBSERVABILITY_SERVICES,
    "administration": {"pgadmin"},
    "backup": {"backup"},
    "restore-verification": {"restore-postgres", "restore-verify"},
}
BACKEND_IMAGE = "forge-backend:${IMAGE_TAG:-latest}"
RENDER_ENVIRONMENT = {"DEPLOY_GROUP_GID": "1000"}


def _services() -> dict[str, dict[str, Any]]:
    return cast(dict[str, dict[str, Any]], COMPOSE["services"])


def _rendered_compose_services(*profiles: str) -> set[str]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is required to render Compose service profiles")
    command = ["docker", "compose", "--env-file", str(DEPLOY / ".env.example")]
    for profile in profiles:
        command.extend(("--profile", profile))
    command.extend(("-f", str(DEPLOY / "compose.yml"), "config", "--services"))
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"COMPOSE_FILE", "COMPOSE_PROFILES"}
    }
    environment.update(RENDER_ENVIRONMENT)
    result = subprocess.run(
        command,
        cwd=DEPLOY,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    return set(result.stdout.split())


def _has_explicit_registry(image: str) -> bool:
    first_component, separator, _ = image.partition("/")
    return bool(separator) and (
        first_component == "localhost"
        or "." in first_component
        or ":" in first_component
        or first_component.lower() != first_component
    )


def test_service_catalog_is_exact() -> None:
    expected = CORE_RENDERED_SERVICES | {
        service for services in PROFILE_SERVICES.values() for service in services
    }
    assert set(_services()) == expected


def test_core_services_have_no_profile_and_profiles_are_exact() -> None:
    for name, service in _services().items():
        if name in CORE_RENDERED_SERVICES:
            assert "profiles" not in service, name
            continue
        (profile,) = service["profiles"]
        assert name in PROFILE_SERVICES[profile], name


def test_default_rendered_compose_contains_only_core_services() -> None:
    assert _rendered_compose_services() == CORE_RENDERED_SERVICES


@pytest.mark.parametrize(
    ("profile", "expected_extras"), sorted(PROFILE_SERVICES.items())
)
def test_rendered_profiles_add_only_declared_services(
    profile: str, expected_extras: set[str]
) -> None:
    assert (
        _rendered_compose_services(profile) - CORE_RENDERED_SERVICES == expected_extras
    )


def test_rendered_default_compose_ignores_inherited_profile_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPOSE_PROFILES", "observability")
    assert _rendered_compose_services() == CORE_RENDERED_SERVICES


def test_prebuilt_images_are_pinned_and_come_from_known_registries() -> None:
    for name, service in _services().items():
        image = service["image"]
        assert (
            ":" in image
            and not image.endswith(":latest")
            or image.endswith("${IMAGE_TAG:-latest}")
        ), name
        if _has_explicit_registry(image):
            assert image.startswith("ghcr.io/danihodovic/celery-exporter:"), name


def test_backend_services_share_image_build_environment_and_secrets() -> None:
    migrate = _services()["django-migrate"]
    for name in (
        "search-index",
        "web",
        "celery-worker",
        "celery-beat",
        "backup",
        "restore-verify",
    ):
        service = _services()[name]
        assert service["image"] == BACKEND_IMAGE, name
        assert service["build"] == migrate["build"], name
    for name in ("search-index", "web", "celery-worker", "celery-beat"):
        assert _services()[name]["secrets"] == migrate["secrets"], name
    assert COMPOSE["x-backend-secrets"] == [
        "django_secret_key",
        "postgres_password",
        "meilisearch_api_key",
        "bexio_access_token",
    ]


def test_backend_environment_uses_file_secrets_and_forge_settings() -> None:
    environment = COMPOSE["x-backend-environment"]
    assert environment["FORGE_ENV"] == "production"
    assert environment["DJANGO_SETTINGS_MODULE"] == "forge.settings"
    assert environment["DJANGO_SECRET_KEY_FILE"] == "/run/secrets/django_secret_key"
    assert environment["POSTGRES_PASSWORD_FILE"] == "/run/secrets/postgres_password"
    assert (
        environment["MEILISEARCH_MASTER_KEY_FILE"] == "/run/secrets/meilisearch_api_key"
    )
    assert environment["BEXIO_ACCESS_TOKEN_FILE"] == "/run/secrets/bexio_access_token"
    assert (
        environment["ALLOWED_HOSTS"]
        == "${APP_DOMAIN},web,${APP_HOST_ALIASES:-localhost,127.0.0.1}"
    )
    assert environment["INTERNAL_METRICS_HOST"] == "web"
    assert (
        environment["CSRF_TRUSTED_ORIGINS"]
        == "${CSRF_TRUSTED_ORIGINS:-https://${APP_DOMAIN}}"
    )
    assert environment["MAINTENANCE_FLAG_FILE"] == "/run/forge/maintenance"
    assert environment["STATIC_ROOT"] == "/static"
    assert environment["LOG_TO_STDOUT"] == "true"
    assert environment["POSTGRES_CONN_MAX_AGE"] == "${POSTGRES_CONN_MAX_AGE:-0}"
    assert "DJANGO_SECRET_KEY" not in environment
    assert "POSTGRES_PASSWORD" not in environment


def test_runtime_services_use_pgbouncer_and_jobs_use_postgres_directly() -> None:
    for name in ("web", "celery-worker", "celery-beat"):
        assert _services()[name]["environment"]["POSTGRES_HOST"] == "pgbouncer", name
    for name in ("django-migrate", "search-index"):
        assert _services()[name]["environment"]["POSTGRES_HOST"] == "postgres", name
    assert (
        _services()["restore-verify"]["environment"]["POSTGRES_HOST"]
        == "restore-postgres"
    )


def test_secret_group_is_added_to_secret_consumers_only() -> None:
    secret_consumers = {
        name for name, service in _services().items() if service.get("secrets")
    }
    group_members = {
        name
        for name, service in _services().items()
        if "${DEPLOY_GROUP_GID}" in service.get("group_add", [])
    }
    assert group_members == secret_consumers
    assert "group_add" not in _services()["node-exporter"]
    assert "group_add" not in _services()["redis"]


def test_web_runs_two_daphne_replicas_by_default() -> None:
    web = _services()["web"]
    assert web["command"] == [
        "daphne",
        "-b",
        "0.0.0.0",
        "-p",
        "8000",
        "forge.asgi:application",
    ]
    assert web["deploy"]["replicas"] == "${WEB_REPLICAS:-2}"
    assert web["read_only"] is True
    assert web["tmpfs"] == ["/tmp"]
    assert "Host: ${APP_DOMAIN}" in web["healthcheck"]["test"]
    assert "http://127.0.0.1:8000/health/live/" in web["healthcheck"]["test"]
    assert web["depends_on"]["django-migrate"] == {
        "condition": "service_completed_successfully"
    }


def test_worker_consumes_default_and_search_reconciliation_queues() -> None:
    worker = _services()["celery-worker"]
    assert worker["command"][:4] == ["celery", "-A", "forge", "worker"]
    assert "--queues=default,search.reconciliation" in worker["command"]
    assert "--concurrency=${CELERY_CONCURRENCY:-2}" in worker["command"]
    assert worker["deploy"]["replicas"] == "${CELERY_REPLICAS:-1}"
    assert worker["stop_grace_period"] == "2m"


def test_beat_is_a_singleton_with_persistent_schedule() -> None:
    beat = _services()["celery-beat"]
    assert beat["command"] == [
        "celery",
        "-A",
        "forge",
        "beat",
        "--loglevel=INFO",
        "--schedule=/data/celerybeat/celerybeat-schedule",
    ]
    assert beat["deploy"]["replicas"] == 1
    assert beat["volumes"] == ["${DATA_ROOT}/celerybeat:/data/celerybeat"]
    assert beat["read_only"] is True


def test_singleton_services_have_one_replica() -> None:
    for name in ("django-migrate", "celery-beat"):
        assert _services()[name]["deploy"]["replicas"] == 1


def test_migration_runs_deployment_checks_before_database_changes() -> None:
    command = _services()["django-migrate"]["command"][-1]
    steps = [step.strip() for step in command.split("&&")]
    assert steps == [
        "python manage.py check --deploy",
        "python manage.py migrate --noinput",
        "python manage.py collectstatic --noinput",
        "python manage.py create_groups",
    ]


def test_search_index_is_an_explicit_one_shot_deployment_service() -> None:
    service = _services()["search-index"]
    migrate = _services()["django-migrate"]
    assert service["profiles"] == ["deployment"]
    assert service["command"] == ["python", "manage.py", "search_index", "--reindex"]
    assert service["environment"] == migrate["environment"]
    assert service["networks"] == migrate["networks"]
    assert service["restart"] == "no"


def test_only_nginx_publishes_ports() -> None:
    publishers = {name for name, service in _services().items() if service.get("ports")}
    assert publishers == {"nginx"}
    nginx = _services()["nginx"]
    assert nginx["ports"] == ["${HTTP_PORT:-80}:80", "${HTTPS_PORT:-443}:443"]
    assert nginx["depends_on"] == {"web": {"condition": "service_healthy"}}
    assert set(nginx["environment"]) == {
        "APP_DOMAIN",
        "MONITORING_DOMAIN",
        "ADMIN_DOMAIN",
        "TLS_CERT_FILE",
        "TLS_KEY_FILE",
        "ADMIN_HTPASSWD_FILE",
    }
    assert "args" not in nginx["build"]
    assert "secrets" not in nginx["build"]


def test_stateful_services_stay_on_internal_networks() -> None:
    assert _services()["postgres"]["networks"] == ["data"]
    assert _services()["restore-postgres"]["networks"] == ["restore-verification"]
    assert COMPOSE["networks"]["restore-verification"] == {"internal": True}
    for name in ("postgres", "redis", "meilisearch", "pgbouncer"):
        assert "ports" not in _services()[name], name


def test_pgbouncer_pools_transactions_from_secret_file() -> None:
    service = _services()["pgbouncer"]
    assert service["image"] == "edoburu/pgbouncer:v1.24.1-p1"
    assert service["entrypoint"] == ["/opt/forge/pgbouncer-entrypoint.sh"]
    assert service["secrets"] == ["postgres_password"]
    assert set(service["networks"]) == {"application", "data"}
    entrypoint = (DEPLOY / "pgbouncer/entrypoint.sh").read_text()
    assert "pool_mode = transaction" in entrypoint
    assert "auth_type = scram-sha-256" in entrypoint
    assert "/run/secrets/postgres_password" in entrypoint


def test_pgbouncer_exporter_uses_secret_file_and_stats_user() -> None:
    service = _services()["pgbouncer-exporter"]
    assert service["secrets"] == ["postgres_password"]
    assert (
        service["environment"]["POSTGRES_PASSWORD_FILE"]
        == "/run/secrets/postgres_password"
    )
    entrypoint = (DEPLOY / "pgbouncer-exporter/entrypoint.sh").read_text()
    assert "dbname=pgbouncer" in entrypoint
    assert "PGBOUNCER_EXPORTER_CONNECTION_STRING" in entrypoint


def test_observability_services_are_profile_gated_and_pinned() -> None:
    for name in OBSERVABILITY_SERVICES:
        service = _services()[name]
        assert service["profiles"] == ["observability"], name
        assert "ports" not in service, name
    assert _services()["prometheus"]["image"] == "prom/prometheus:v3.12.0"
    assert _services()["grafana"]["image"] == "grafana/grafana:13.0.1-security-01"
    assert _services()["loki"]["image"] == "grafana/loki:3.7.2"
    assert _services()["alloy"]["image"] == "grafana/alloy:v1.17.0"
    assert (
        _services()["celery-exporter"]["image"]
        == "ghcr.io/danihodovic/celery-exporter:0.12.2"
    )


def test_prometheus_mounts_rendered_rules_read_only_and_accepts_remote_write() -> None:
    prometheus = _services()["prometheus"]
    assert "--web.enable-remote-write-receiver" in prometheus["command"]
    assert (
        "--storage.tsdb.retention.time=${PROMETHEUS_RETENTION:-45d}"
        in prometheus["command"]
    )
    assert (
        "--storage.tsdb.retention.size=${PROMETHEUS_RETENTION_SIZE:-10GB}"
        in prometheus["command"]
    )
    assert (
        "${DATA_ROOT}/runtime/prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro"
        in prometheus["volumes"]
    )
    assert (
        "./prometheus/recording-rules.yml:/etc/prometheus/recording-rules.yml:ro"
        in prometheus["volumes"]
    )
    assert prometheus["secrets"] == ["meilisearch_api_key"]


def test_alertmanager_uses_rendered_config_secrets_and_dedicated_egress() -> None:
    alertmanager = _services()["alertmanager"]
    assert set(alertmanager["secrets"]) == {"teams_workflow_url", "smtp_password"}
    assert (
        "${DATA_ROOT}/runtime/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro"
        in alertmanager["volumes"]
    )
    assert set(alertmanager["networks"]) == {"observability", "alerting-egress"}
    assert "--enable-feature=utf8-strict-mode" in alertmanager["command"]
    assert COMPOSE["secrets"]["smtp_password"]["file"] == (
        "${ALERT_SMTP_PASSWORD_FILE:-${SECRETS_DIR:-./secrets}/smtp_password.txt}"
    )


def test_alloy_host_access_is_explicit_and_isolated() -> None:
    alloy = _services()["alloy"]
    assert alloy["privileged"] is True
    assert alloy["read_only"] is True
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in alloy["volumes"]
    assert alloy["networks"] == ["observability"]


def test_node_exporter_reads_host_and_textfile_metrics() -> None:
    node_exporter = _services()["node-exporter"]
    assert node_exporter["pid"] == "host"
    assert "/:/host:ro,rslave" in node_exporter["volumes"]
    assert (
        "${DATA_ROOT}/runtime/node-exporter:/var/lib/node_exporter/textfile:ro"
        in node_exporter["volumes"]
    )


def test_blackbox_exporter_reaches_public_and_internal_targets() -> None:
    assert set(_services()["blackbox-exporter"]["networks"]) == {
        "observability",
        "ingress",
        "application",
    }
    assert _services()["blackbox-exporter"]["extra_hosts"] == [
        "${APP_DOMAIN}:host-gateway"
    ]
    assert (
        "${TLS_CERT_FILE}:/run/tls/tls.crt:ro"
        in _services()["blackbox-exporter"]["volumes"]
    )


def test_pushgateway_is_reachable_from_application_jobs() -> None:
    pushgateway = _services()["pushgateway"]
    assert set(pushgateway["networks"]) == {"application", "observability"}
    for name in ("backup", "restore-verify"):
        assert "observability" in _services()[name]["networks"], name
    assert (
        COMPOSE["x-backend-environment"]["PUSHGATEWAY_URL"]
        == "${PUSHGATEWAY_URL:-http://pushgateway:9091}"
    )


def test_pgadmin_is_internal_and_profile_gated() -> None:
    pgadmin = _services()["pgadmin"]
    assert pgadmin["profiles"] == ["administration"]
    assert set(pgadmin["networks"]) == {"ingress", "data"}
    assert pgadmin["secrets"] == ["pgadmin_password"]
    assert "ports" not in pgadmin
    servers = yaml.safe_load((DEPLOY / "pgadmin/servers.json").read_text())
    assert servers["Servers"]["1"]["Host"] == "postgres"
    assert servers["Servers"]["1"]["Username"] == "forge"


def test_backup_and_restore_verification_are_isolated_one_shots() -> None:
    backup = _services()["backup"]
    assert backup["entrypoint"] == ["/bin/sh", "/app/deploy/backup/backup.sh"]
    assert backup["volumes"] == [
        "${DATA_ROOT}/backups:/backups/local",
        "${BACKUP_SHARE}:/backups/share",
    ]
    assert backup["restart"] == "no"
    verify = _services()["restore-verify"]
    assert verify["entrypoint"] == ["/bin/sh", "/app/deploy/backup/restore-verify.sh"]
    assert verify["command"] == ["/restore/source"]
    assert "${RESTORE_BACKUP}:/restore/source:ro" in verify["volumes"]
    assert "restore_postgres_data:/restore/postgres:ro" in verify["volumes"]
    assert set(verify["networks"]) == {"restore-verification", "observability"}
    assert COMPOSE["volumes"] == {"restore_postgres_data": None}


def test_every_secret_lives_in_secrets_dir_and_has_an_example_template() -> None:
    for name, secret in COMPOSE["secrets"].items():
        match = re.fullmatch(
            r"(\$\{ALERT_SMTP_PASSWORD_FILE:-)?\$\{SECRETS_DIR:-\./secrets\}/(\w+\.txt)\}?",
            secret["file"],
        )
        assert match, (name, secret["file"])
        assert (DEPLOY / "secrets" / f"{match.group(2)}.example").exists(), name
    referenced = {
        secret
        for service in _services().values()
        for secret in service.get("secrets", [])
    }
    assert referenced == set(COMPOSE["secrets"])


def test_env_example_has_no_resolved_group_gid_and_documents_scaling() -> None:
    text = (DEPLOY / ".env.example").read_text()
    keys = dict(re.findall(r"^([A-Z_]+)=(.*)$", text, re.MULTILINE))
    assert "DEPLOY_GROUP_GID" not in keys
    assert "SOURCE_REVISION" not in keys
    assert keys["DEPLOY_GROUP"] == "forge-deploy"
    assert keys["WEB_REPLICAS"] == "2"
    assert keys["CELERY_REPLICAS"] == "1"
    assert keys["DATA_ROOT"] == "/srv/forge/data"
    assert keys["ALERT_TEAMS_ENABLED"] == "false"
    assert keys["ALERT_SMTP_PASSWORD_FILE"] == "/dev/null"
    assert keys["OBSERVABILITY_RUNBOOK_BASE_URL"].startswith(
        "https://github.com/EliasBauer/Forge/"
    )
    assert set(keys["NO_PROXY"].split(",")) >= {
        "pushgateway",
        "prometheus",
        "grafana",
        "loki",
        "web",
        "nginx",
    }
