from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

DEPLOY = Path(__file__).resolve().parents[1]
ALERT_TEMPLATE = DEPLOY / "prometheus/alerts.yml.tmpl"
RUNBOOK = DEPLOY / "runbooks/alerts.md"
REQUIRED_ANNOTATIONS = {
    "summary",
    "impact",
    "first_action",
    "dashboard_url",
    "runbook_url",
}
REQUIRED_LABELS = {"severity", "service", "notification_scope", "alert_family"}
MAINTENANCE_SENSITIVE_TOKENS = (
    "PublicProbe",
    "Graphql",
    "ApiLatency",
    "Postgres",
    "Redis",
    "Meilisearch",
    "Pgbouncer",
    "Celery",
    "ApplicationContainerOom",
)
DASHBOARD_ALERTS = {
    "forge-api": {
        "ForgePublicProbeDown",
        "ForgeTlsExpiryWarning",
        "ForgeTlsExpiryCritical",
        "ForgeGraphqlServerFaultsWarning",
        "ForgeGraphqlServerFaultsCritical",
        "ForgeGraphqlErrorRatioInfo",
        "ForgeApiLatencyWarning",
        "ForgeApiLatencyCritical",
    },
    "forge-postgres-pgbouncer": {
        "ForgePostgresDown",
        "ForgePgbouncerSaturation",
        "ForgePgbouncerWaitingClients",
    },
    "forge-async-redis": {
        "ForgeRedisDown",
        "ForgeCeleryQueueAgeWarning",
        "ForgeCeleryQueueAgeCritical",
        "ForgeCeleryNoWorker",
        "ForgeCeleryFailureRatio",
    },
    "forge-search": {"ForgeMeilisearchTargetDown", "ForgeMeilisearchUnavailable"},
    "forge-host-containers": {
        "ForgeHostCpuHigh",
        "ForgeMemoryLow",
        "ForgeMemoryCritical",
        "ForgeApplicationContainerOom",
        "ForgeFilesystemLow",
        "ForgeFilesystemPredictedFull",
        "ForgeFilesystemCritical",
    },
    "forge-continuity": {
        "ForgeMaintenanceActive",
        "ForgeMaintenanceOverrun",
        "ForgeBackupTelemetryMissing",
        "ForgeBackupStale",
        "ForgeBackupCritical",
        "ForgeBackupTransferFailed",
        "ForgeRestoreVerificationMissing",
        "ForgeRestoreVerificationStale",
        "ForgeRestoreVerificationCritical",
        "ForgeTelemetryTargetDown",
        "ForgeRuleEvaluationFailures",
        "ForgeNotificationDeliveryFailures",
    },
}
# (severity, notification_scope, service, alert_family, for)
ALERT_MATRIX: dict[str, tuple[str, str, str, str, str]] = {
    "ForgeMaintenanceActive": ("info", "none", "maintenance", "maintenance", "0m"),
    "ForgeMaintenanceOverrun": (
        "critical",
        "always",
        "maintenance",
        "maintenance",
        "1m",
    ),
    "ForgePublicProbeDown": ("critical", "always", "public-api", "public-probe", "2m"),
    "ForgeTlsExpiryWarning": (
        "warning",
        "business_hours",
        "public-api",
        "tls-expiry",
        "15m",
    ),
    "ForgeTlsExpiryCritical": ("critical", "always", "public-api", "tls-expiry", "5m"),
    "ForgeGraphqlServerFaultsWarning": (
        "warning",
        "business_hours",
        "api",
        "graphql-server-faults",
        "0m",
    ),
    "ForgeGraphqlServerFaultsCritical": (
        "critical",
        "business_hours",
        "api",
        "graphql-server-faults",
        "0m",
    ),
    "ForgeGraphqlErrorRatioInfo": ("info", "none", "api", "graphql-error-ratio", "15m"),
    "ForgeApiLatencyWarning": (
        "warning",
        "business_hours",
        "api",
        "api-latency",
        "15m",
    ),
    "ForgeApiLatencyCritical": (
        "critical",
        "business_hours",
        "api",
        "api-latency",
        "10m",
    ),
    "ForgePostgresDown": (
        "critical",
        "always",
        "postgres",
        "postgres-availability",
        "2m",
    ),
    "ForgeRedisDown": ("critical", "always", "redis", "redis-availability", "2m"),
    "ForgeMeilisearchTargetDown": (
        "warning",
        "business_hours",
        "meilisearch",
        "meilisearch-availability",
        "2m",
    ),
    "ForgeMeilisearchUnavailable": (
        "critical",
        "business_hours",
        "meilisearch",
        "meilisearch-availability",
        "5m",
    ),
    "ForgePgbouncerSaturation": (
        "warning",
        "business_hours",
        "pgbouncer",
        "pgbouncer-capacity",
        "10m",
    ),
    "ForgePgbouncerWaitingClients": (
        "critical",
        "business_hours",
        "pgbouncer",
        "pgbouncer-capacity",
        "5m",
    ),
    "ForgeCeleryQueueAgeWarning": (
        "warning",
        "business_hours",
        "celery",
        "celery-queue-age",
        "5m",
    ),
    "ForgeCeleryQueueAgeCritical": (
        "critical",
        "business_hours",
        "celery",
        "celery-queue-age",
        "5m",
    ),
    "ForgeCeleryNoWorker": (
        "critical",
        "business_hours",
        "celery",
        "celery-workers",
        "5m",
    ),
    "ForgeCeleryFailureRatio": (
        "info",
        "none",
        "celery",
        "celery-failure-ratio",
        "10m",
    ),
    "ForgeHostCpuHigh": ("warning", "business_hours", "host", "host-cpu", "20m"),
    "ForgeMemoryLow": ("warning", "business_hours", "host", "host-memory", "10m"),
    "ForgeMemoryCritical": ("critical", "always", "host", "host-memory", "5m"),
    "ForgeApplicationContainerOom": (
        "critical",
        "always",
        "containers",
        "container-oom",
        "0m",
    ),
    "ForgeFilesystemLow": (
        "warning",
        "business_hours",
        "host",
        "host-filesystem",
        "15m",
    ),
    "ForgeFilesystemPredictedFull": (
        "warning",
        "business_hours",
        "host",
        "host-filesystem-prediction",
        "15m",
    ),
    "ForgeFilesystemCritical": ("critical", "always", "host", "host-filesystem", "5m"),
    "ForgeBackupTelemetryMissing": (
        "warning",
        "business_hours",
        "backup",
        "backup",
        "30m",
    ),
    "ForgeBackupStale": ("warning", "business_hours", "backup", "backup", "15m"),
    "ForgeBackupCritical": ("critical", "always", "backup", "backup", "15m"),
    "ForgeBackupTransferFailed": (
        "critical",
        "always",
        "backup",
        "backup-transfer",
        "5m",
    ),
    "ForgeRestoreVerificationMissing": (
        "warning",
        "business_hours",
        "restore",
        "restore-verification",
        "30m",
    ),
    "ForgeRestoreVerificationStale": (
        "warning",
        "business_hours",
        "restore",
        "restore-verification",
        "15m",
    ),
    "ForgeRestoreVerificationCritical": (
        "critical",
        "business_hours",
        "restore",
        "restore-verification",
        "15m",
    ),
    "ForgeTelemetryTargetDown": (
        "critical",
        "always",
        "observability",
        "telemetry-target",
        "5m",
    ),
    "ForgeRuleEvaluationFailures": (
        "critical",
        "always",
        "prometheus",
        "rule-evaluation",
        "1m",
    ),
    "ForgeNotificationDeliveryFailures": (
        "critical",
        "always",
        "alertmanager",
        "notification-delivery",
        "1m",
    ),
}


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def _alert_rules() -> list[dict[str, Any]]:
    groups = cast(dict[str, Any], _load(ALERT_TEMPLATE))["groups"]
    return [rule for group in groups for rule in group["rules"] if "alert" in rule]


def _prometheus_config() -> dict[str, Any]:
    return cast(dict[str, Any], _load(DEPLOY / "prometheus/prometheus.yml"))


# --- alloy ---


def test_alloy_log_labels_are_bounded_and_level_is_parsed_at_processing_time() -> None:
    text = (DEPLOY / "alloy/config.alloy").read_text()
    for label in ("compose_project", "compose_service", "container", "stream"):
        assert re.search(rf'target_label\s*=\s*"{label}"', text)
    assert 'raw_level = "levelname"' in text
    assert (
        'expression = "^(?P<level>TRACE|DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)$"'
        in text
    )
    assert "stage.labels" in text and 'level = ""' in text
    assert "user" not in text and "request_uri" not in text


def _alloy_level_from_raw_line(config: str, line: str) -> str | None:
    regex_stages = re.findall(r"stage\.regex\s*\{(.*?)\n\s*\}", config, re.DOTALL)
    expressions = [
        cast(re.Match[str], re.search(r'expression\s*=\s*"([^"]+)"', stage))
        .group(1)
        .replace("\\\\", "\\")
        for stage in regex_stages
    ]
    assert len(expressions) == 2
    json_stage, celery_fallback = expressions
    try:
        decoded = json.loads(line)
    except json.JSONDecodeError:
        raw_level = None
    else:
        raw_level = decoded.get("levelname") if isinstance(decoded, dict) else None
    extracted: dict[str, str] = {}
    if isinstance(raw_level, str) and (match := re.fullmatch(json_stage, raw_level)):
        extracted.update(match.groupdict())
    if match := re.search(celery_fallback, line):
        extracted.update(match.groupdict())
    return extracted.get("level")


@pytest.mark.parametrize(
    ("line", "expected_level"),
    (
        ('{"levelname":"ERROR","message":"database unavailable"}', "ERROR"),
        (
            "[2026-08-29 12:00:00,000: ERROR/ForkPoolWorker-1] Task bexio.sync raised unexpected: RuntimeError()",  # noqa: E501
            "ERROR",
        ),
        (
            "[2026-08-29 12:00:00,000: CRITICAL/MainProcess] Unrecoverable worker failure",  # noqa: E501
            "CRITICAL",
        ),
        ("[2026-08-29 12:00:00,000: INFO/MainProcess] beat: Starting...", None),
    ),
)
def test_alloy_extracts_severity_from_json_and_celery_plaintext_logs(
    line: str, expected_level: str | None
) -> None:
    config = (DEPLOY / "alloy/config.alloy").read_text()
    assert _alloy_level_from_raw_line(config, line) == expected_level


def test_alloy_collects_allowlisted_compose_cadvisor_metrics_and_ships_to_loki() -> (
    None
):
    text = (DEPLOY / "alloy/config.alloy").read_text()
    assert "prometheus.exporter.cadvisor" in text
    assert '"container_label_com_docker_compose_project"' in text
    assert '"container_label_com_docker_compose_service"' in text
    assert 'url = "http://prometheus:9090/api/v1/write"' in text
    assert 'url = "http://loki:3100/loki/api/v1/push"' in text
    compose = _load(DEPLOY / "compose.yml")
    assert "promtail" not in compose["services"]


# --- alertmanager ---


def test_alertmanager_template_routes_teams_and_email_notifications() -> None:
    text = (DEPLOY / "alertmanager/alertmanager.yml.tmpl").read_text()
    config = yaml.safe_load(text)
    assert text.count("# TEAMS_ONLY") == 5
    assert text.count("# SMTP_AUTH_ONLY") == 2
    assert config["global"]["smtp_auth_password_file"] == "/run/secrets/smtp_password"
    route = config["route"]
    assert route["receiver"] == "sink"
    assert route["group_by"] == ["alertname", "service", "severity"]
    assert route["routes"] == [
        {
            "receiver": "operations",
            "matchers": ['alertname="ForgeNotificationTest"'],
            "group_wait": "0s",
            "group_interval": "1s",
            "repeat_interval": "1h",
        },
        {
            "receiver": "operations",
            "matchers": ['notification_scope="always"'],
            "repeat_interval": "1h",
        },
        {
            "receiver": "operations",
            "matchers": ['notification_scope="business_hours"', 'severity="critical"'],
            "active_time_intervals": ["business-hours"],
            "repeat_interval": "1h",
        },
        {
            "receiver": "operations",
            "matchers": ['notification_scope="business_hours"', 'severity="warning"'],
            "active_time_intervals": ["business-hours"],
            "repeat_interval": "4h",
        },
    ]
    operations = config["receivers"][1]
    assert (
        operations["msteamsv2_configs"][0]["webhook_url_file"]
        == "/run/secrets/teams_workflow_url"
    )
    assert operations["email_configs"][0]["headers"]["Subject"].startswith("[Forge][")


def test_alertmanager_inhibits_maintenance_sensitive_alerts_and_defines_local_business_hours() -> (  # noqa: E501
    None
):
    config = yaml.safe_load((DEPLOY / "alertmanager/alertmanager.yml.tmpl").read_text())
    assert config["inhibit_rules"][0] == {
        "source_matchers": ['alertname="ForgeMaintenanceActive"'],
        "target_matchers": ['maintenance_sensitive="true"'],
        "equal": ["environment"],
    }
    assert config["inhibit_rules"][1]["source_matchers"] == ['root_cause="true"']
    critical = config["inhibit_rules"][2]
    assert critical["source_matchers"] == ['severity="critical"']
    assert "mountpoint" in critical["equal"] and "alert_family" in critical["equal"]
    intervals = config["time_intervals"]
    assert intervals == [
        {
            "name": "business-hours",
            "time_intervals": [
                {
                    "weekdays": ["monday:friday"],
                    "times": [{"start_time": "07:00", "end_time": "18:00"}],
                    "location": "Europe/Zurich",
                }
            ],
        }
    ]


def test_notification_test_helper_waits_longer_than_the_test_route_group_wait() -> None:
    config = yaml.safe_load((DEPLOY / "alertmanager/alertmanager.yml.tmpl").read_text())
    helper = (DEPLOY / "scripts/send-test-alert.sh").read_text()
    sleep_seconds = int(
        cast(re.Match[str], re.search(r"^sleep ([0-9]+)$", helper, re.MULTILINE)).group(
            1
        )
    )
    assert sleep_seconds > int(
        config["route"]["routes"][0]["group_wait"].removesuffix("s")
    )


# --- prometheus ---


def test_prometheus_scrapes_every_forge_target_and_sends_alerts() -> None:
    config = _prometheus_config()
    assert config["global"]["external_labels"] == {"environment": "production"}
    assert config["alerting"] == {
        "alertmanagers": [{"static_configs": [{"targets": ["alertmanager:9093"]}]}]
    }
    assert config["rule_files"] == [
        "/etc/prometheus/alerts.yml",
        "/etc/prometheus/recording-rules.yml",
    ]
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}
    assert set(jobs) == {
        "prometheus",
        "alertmanager",
        "forge-web",
        "postgres",
        "redis",
        "celery",
        "nginx",
        "node",
        "pgbouncer",
        "alloy",
        "loki",
        "blackbox",
        "meilisearch",
        "pushgateway",
    }
    assert jobs["forge-web"]["dns_sd_configs"] == [
        {"names": ["web"], "type": "A", "port": 8000, "refresh_interval": "15s"}
    ]
    assert jobs["meilisearch"]["authorization"] == {
        "type": "Bearer",
        "credentials_file": "/run/secrets/meilisearch_api_key",
    }
    assert jobs["blackbox"]["file_sd_configs"] == [
        {"files": ["/etc/prometheus/targets/blackbox-targets.yml"]}
    ]
    assert jobs["pushgateway"]["honor_labels"] is True
    assert "legacy" not in (DEPLOY / "prometheus/prometheus.yml").read_text()


def test_prometheus_recording_rules_define_forge_rollups() -> None:
    groups = _load(DEPLOY / "prometheus/recording-rules.yml")["groups"]
    assert [group["name"] for group in groups] == ["forge-api-recording"]
    rules = {rule["record"]: rule["expr"] for rule in groups[0]["rules"]}
    assert set(rules) == {
        "forge:api_requests:rate5m",
        "forge:graphql_server_faults:rate5m",
        "forge:api_request_duration_seconds:p95_5m",
        "forge:graphql_request_duration_seconds:p95_5m",
        "forge:graphql_errors:ratio5m",
    }
    assert (
        rules["forge:api_requests:rate5m"]
        == "sum by (api) (rate(forge_api_requests_total[5m]))"
    )
    assert rules["forge:graphql_errors:ratio5m"].endswith(
        "and (sum(rate(graphql_requests_total[5m])) > 0)"
    )
    assert not any("or vector(0)" in expr for expr in rules.values())


def test_prometheus_recording_rule_fixture_covers_ratio_semantics() -> None:
    fixture = _load(DEPLOY / "prometheus/recording-rules.test.yml")
    assert fixture["rule_files"] == ["recording-rules.yml"]
    cases = {case["name"]: case for case in fixture["tests"]}
    assert set(cases) == {"zero_traffic_preserves_unknown", "active_traffic_ratios"}
    zero = {
        result["expr"]: result["exp_samples"]
        for result in cases["zero_traffic_preserves_unknown"]["promql_expr_test"]
    }
    assert zero["forge:graphql_errors:ratio5m"] == []
    active = {
        result["expr"]: result["exp_samples"]
        for result in cases["active_traffic_ratios"]["promql_expr_test"]
    }
    assert active["forge:graphql_errors:ratio5m"] == [
        {"labels": "forge:graphql_errors:ratio5m", "value": 0.1}
    ]


def test_blackbox_modules_probe_public_and_internal_health() -> None:
    config = _load(DEPLOY / "blackbox/blackbox.yml")
    assert set(config["modules"]) == {
        "https_2xx",
        "graphql_health",
        "internal_http_2xx",
    }
    graphql = config["modules"]["graphql_health"]["http"]
    assert graphql["fail_if_not_ssl"] is True
    for module in ("https_2xx", "graphql_health"):
        assert config["modules"][module]["http"]["tls_config"] == {
            "ca_file": "/run/tls/tls.crt"
        }
    assert "tls_config" not in config["modules"]["internal_http_2xx"]["http"]
    pattern = re.compile(graphql["fail_if_body_not_matches_regexp"][0])
    assert pattern.match('{"data":{"__typename":"Query"}}')
    assert not pattern.match('{"data":{"__typename":"Query"},"errors":[{}]}')
    targets = (DEPLOY / "prometheus/blackbox-targets.yml.tmpl").read_text()
    assert "https://__APP_DOMAIN__/health/live/" in targets
    assert "operationName=HealthProbe" in targets
    assert "http://meilisearch:7700/health" in targets
    assert yaml.safe_load(targets)[2]["labels"] == {
        "module": "internal_http_2xx",
        "probe": "meilisearch_health",
    }


def test_loki_retains_seven_days_under_the_forge_index_prefix() -> None:
    config = _load(DEPLOY / "loki/loki.yml")
    assert config["limits_config"]["retention_period"] == "168h"
    assert config["schema_config"]["configs"][0]["index"]["prefix"] == "forge_index_"
    assert config["compactor"]["retention_enabled"] is True
    assert config["analytics"]["reporting_enabled"] is False


# --- alert catalogue ---


def test_alert_catalog_matches_approved_rule_matrix() -> None:
    rules = _alert_rules()
    assert len(rules) == len(ALERT_MATRIX) == 37
    assert {rule["alert"] for rule in rules} == set(ALERT_MATRIX)
    for rule in rules:
        severity, scope, service, family, duration = ALERT_MATRIX[rule["alert"]]
        assert rule["labels"]["severity"] == severity, rule["alert"]
        assert rule["labels"]["notification_scope"] == scope, rule["alert"]
        assert rule["labels"]["service"] == service, rule["alert"]
        assert rule["labels"]["alert_family"] == family, rule["alert"]
        assert rule["for"] == duration, rule["alert"]


def test_alert_labels_follow_routing_and_inhibition_policy() -> None:
    rules = {rule["alert"]: rule for rule in _alert_rules()}
    maintenance_sensitive = {
        name
        for name in ALERT_MATRIX
        if any(token in name for token in MAINTENANCE_SENSITIVE_TOKENS)
    }
    assert {
        name
        for name, rule in rules.items()
        if rule["labels"].get("maintenance_sensitive") == "true"
    } == maintenance_sensitive
    for rule in rules.values():
        assert REQUIRED_LABELS <= set(rule["labels"])
    for name, dependency in (
        ("ForgePostgresDown", "postgres"),
        ("ForgeRedisDown", "redis"),
    ):
        assert rules[name]["labels"]["root_cause"] == "true"
        assert rules[name]["labels"]["dependency"] == dependency
    assert not any(
        "root_cause" in rule["labels"]
        for name, rule in rules.items()
        if name not in {"ForgePostgresDown", "ForgeRedisDown"}
    )


def test_alert_expressions_enforce_forge_metric_names_and_traffic_floors() -> None:
    by_name = {rule["alert"]: rule for rule in _alert_rules()}
    text = ALERT_TEMPLATE.read_text()
    assert "legacy" not in text.lower()
    assert (
        by_name["ForgeMaintenanceActive"]["expr"]
        == "forge_maintenance_suppress_until_timestamp_seconds > time()"
    )
    assert 'absent(up{job="forge-web"})' in by_name["ForgePublicProbeDown"]["expr"]
    assert "forge-web" not in by_name["ForgeTelemetryTargetDown"]["expr"]
    assert "blackbox" in by_name["ForgeTelemetryTargetDown"]["expr"]
    assert (
        "sum(increase(graphql_requests_total[15m])) >= 20"
        in by_name["ForgeGraphqlErrorRatioInfo"]["expr"]
    )
    assert by_name["ForgeApiLatencyCritical"]["expr"] == (
        "forge:api_request_duration_seconds:p95_5m > 3 and on(api) sum by (api) (increase(forge_api_requests_total[10m])) >= 20"  # noqa: E501
    )
    assert (
        'compose_service=~"web|celery-worker|postgres|redis|meilisearch"'
        in by_name["ForgeApplicationContainerOom"]["expr"]
    )
    assert (
        "max(forge_celery_oldest_task_age_seconds) > 600"
        == by_name["ForgeCeleryQueueAgeWarning"]["expr"]
    )
    assert (
        "backup_last_success_timestamp_seconds"
        in by_name["ForgeBackupCritical"]["expr"]
    )


def test_alert_annotations_and_runbook_are_complete() -> None:
    dashboard_by_alert = {
        alert: dashboard
        for dashboard, alerts in DASHBOARD_ALERTS.items()
        for alert in alerts
    }
    assert set(dashboard_by_alert) == set(ALERT_MATRIX)
    runbook = RUNBOOK.read_text()
    headings = re.findall(r"^## ([A-Za-z0-9]+)$", runbook, re.MULTILINE)
    assert set(headings) == set(ALERT_MATRIX)
    assert len(headings) == len(ALERT_MATRIX)
    for rule in _alert_rules():
        name = rule["alert"]
        annotations = rule["annotations"]
        assert set(annotations) == REQUIRED_ANNOTATIONS, name
        assert all(str(value).strip() for value in annotations.values()), name
        assert (
            annotations["dashboard_url"]
            == f"https://__MONITORING_DOMAIN__/d/{dashboard_by_alert[name]}"
        ), name
        assert (
            annotations["runbook_url"]
            == f"__RUNBOOK_BASE_URL__/alerts.md#{name.lower()}"
        ), name
        section = runbook.split(f"## {name}\n", 1)[1].split("\n## ", 1)[0]
        assert re.search(r"^### Impact\n\S", section, re.MULTILINE), name
        assert re.search(
            r"^### First three checks\n1\. .+\n2\. .+\n3\. .+$", section, re.MULTILINE
        ), name
        assert re.search(r"^### Recovery criteria\n\S", section, re.MULTILINE), name
        assert re.search(r"^### Escalation\n\S", section, re.MULTILINE), name


def test_alert_promtool_fixture_is_consistent_with_the_catalog() -> None:
    fixture = _load(DEPLOY / "prometheus/tests/alerts.test.yml")
    assert fixture["rule_files"] == ["../recording-rules.yml", "../alerts.yml.tmpl"]
    assert fixture["evaluation_interval"] == "1m"
    rules = {rule["alert"]: rule for rule in _alert_rules()}
    cases = {case["name"]: case for case in fixture["tests"]}
    assert set(cases) == {
        "maintenance_active_and_overrun",
        "backup_telemetry_missing",
        "graphql_warning_only",
        "graphql_critical",
        "tls_warning",
        "tls_critical",
        "meilisearch_health_failed",
        "meilisearch_health_absent",
        "disk_warning",
        "disk_critical",
        "maintenance_recovery",
        "fresh_backup",
        "api_latency_same_api",
        "api_latency_cross_api",
        "telemetry_blackbox_down",
        "public_probe_web_absent",
        "public_probe_down",
        "public_probe_absent",
        "telemetry_blackbox_absent",
        "backup_first_transfer_failure",
        "backup_never_succeeded",
        "restore_never_verified",
    }
    covered: set[str] = set()
    for name, case in cases.items():
        assert case["interval"] == "1m", name
        for result in case["alert_rule_test"]:
            assert result["alertname"] in rules, (name, result["alertname"])
            for expected in result["exp_alerts"]:
                covered.add(result["alertname"])
                assert (
                    expected["exp_annotations"]
                    == rules[result["alertname"]]["annotations"]
                ), (name, result["alertname"])
    assert {
        "ForgeMaintenanceActive",
        "ForgeMaintenanceOverrun",
        "ForgePublicProbeDown",
        "ForgeTlsExpiryWarning",
        "ForgeTlsExpiryCritical",
        "ForgeGraphqlServerFaultsWarning",
        "ForgeGraphqlServerFaultsCritical",
        "ForgeApiLatencyCritical",
        "ForgeMeilisearchUnavailable",
        "ForgeFilesystemLow",
        "ForgeFilesystemCritical",
        "ForgeBackupTelemetryMissing",
        "ForgeBackupTransferFailed",
        "ForgeBackupCritical",
        "ForgeRestoreVerificationCritical",
        "ForgeTelemetryTargetDown",
    } <= covered
    cross_api = {
        item["series"] for item in cases["api_latency_cross_api"]["input_series"]
    }
    assert cross_api == {
        'forge:api_request_duration_seconds:p95_5m{api="graphql"}',
        'forge_api_requests_total{api="auth",status="200"}',
    }


# --- render-observability-config.sh ---


def _render_env(tmp_path: Path) -> dict[str, str]:
    data_root = tmp_path / "data"
    data_root.mkdir()
    return {
        **os.environ,
        "ENV_FILE": str(tmp_path / "missing.env"),
        "DATA_ROOT": str(data_root),
        "APP_DOMAIN": "app.example.test",
        "MONITORING_DOMAIN": "monitoring.example.test",
        "ALERT_TEAMS_ENABLED": "true",
        "ALERT_SMTP_SMARTHOST": "smtp.example.test:587",
        "ALERT_SMTP_FROM": "alerts@example.test",
        "ALERT_SMTP_USERNAME": "alerts@example.test",
        "ALERT_SMTP_AUTH_ENABLED": "true",
        "ALERT_SMTP_REQUIRE_TLS": "true",
        "ALERT_EMAIL_TO": "ops@example.test",
        "OBSERVABILITY_RUNBOOK_BASE_URL": "https://docs.example.test/forge",
        "ALERT_SMTP_PASSWORD": "must-not-appear-in-rendered-config",
    }


def test_render_observability_config_writes_complete_atomic_config_set(
    tmp_path: Path,
) -> None:
    env = _render_env(tmp_path)
    subprocess.run(
        [str(DEPLOY / "scripts/render-observability-config.sh")], check=True, env=env
    )
    runtime = Path(env["DATA_ROOT"]) / "runtime"
    outputs = sorted(
        path.relative_to(runtime).as_posix()
        for path in runtime.rglob("*")
        if path.is_file()
    )
    assert outputs == [
        "alertmanager/alertmanager.yml",
        "prometheus/alerts.yml",
        "prometheus/blackbox-targets.yml",
    ]
    for relative in outputs:
        text = (runtime / relative).read_text()
        assert not any(
            placeholder in text
            for placeholder in (
                "__APP_DOMAIN__",
                "__MONITORING_DOMAIN__",
                "__ALERT_",
                "__RUNBOOK_BASE_URL__",
            )
        )
        assert env["ALERT_SMTP_PASSWORD"] not in text
        assert stat.S_IMODE((runtime / relative).stat().st_mode) == 0o644
    targets = yaml.safe_load((runtime / "prometheus/blackbox-targets.yml").read_text())
    assert targets[0]["targets"] == ["https://app.example.test/health/live/"]
    rendered = yaml.safe_load((runtime / "alertmanager/alertmanager.yml").read_text())
    assert rendered["global"]["smtp_auth_username"] == "alerts@example.test"
    assert rendered["global"]["smtp_require_tls"] is True
    assert (
        rendered["receivers"][1]["msteamsv2_configs"][0]["webhook_url_file"]
        == "/run/secrets/teams_workflow_url"
    )
    alerts = yaml.safe_load((runtime / "prometheus/alerts.yml").read_text())
    first = alerts["groups"][0]["rules"][0]["annotations"]
    assert (
        first["dashboard_url"] == "https://monitoring.example.test/d/forge-continuity"
    )
    assert first["runbook_url"].startswith("https://docs.example.test/forge/alerts.md#")


def test_render_observability_config_disables_teams_and_smtp_auth_independently(
    tmp_path: Path,
) -> None:
    env = _render_env(tmp_path)
    env.update(
        {
            "ALERT_TEAMS_ENABLED": "false",
            "ALERT_SMTP_AUTH_ENABLED": "false",
            "ALERT_SMTP_REQUIRE_TLS": "false",
            "ALERT_SMTP_USERNAME": "",
        }
    )
    subprocess.run(
        [str(DEPLOY / "scripts/render-observability-config.sh")], check=True, env=env
    )
    rendered = yaml.safe_load(
        (Path(env["DATA_ROOT"]) / "runtime/alertmanager/alertmanager.yml").read_text()
    )
    assert "msteamsv2_configs" not in rendered["receivers"][1]
    assert rendered["receivers"][1]["email_configs"][0]["to"] == "ops@example.test"
    assert "smtp_auth_username" not in rendered["global"]
    assert "smtp_auth_password_file" not in rendered["global"]
    assert rendered["global"]["smtp_require_tls"] is False


def test_render_observability_config_rejects_invalid_input_without_replacement(
    tmp_path: Path,
) -> None:
    env = _render_env(tmp_path)
    runtime = Path(env["DATA_ROOT"]) / "runtime"
    (runtime / "prometheus").mkdir(parents=True)
    (runtime / "prometheus/alerts.yml").write_text("previous\n")
    env["ALERT_SMTP_SMARTHOST"] = "not a host"
    result = subprocess.run(
        [str(DEPLOY / "scripts/render-observability-config.sh")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ALERT_SMTP_SMARTHOST must be a safe host and numeric port" in result.stderr
    assert (runtime / "prometheus/alerts.yml").read_text() == "previous\n"
    assert not (runtime / "alertmanager").exists()
