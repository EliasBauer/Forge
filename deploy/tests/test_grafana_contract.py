from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

import pytest
import yaml

DEPLOY = Path(__file__).resolve().parents[1]
SCRIPTS = DEPLOY / "grafana/scripts"
DASHBOARD_ROOT = DEPLOY / "grafana/dashboards"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_dashboards  # noqa: E402
from dashboard_specs import DASHBOARDS  # noqa: E402
from dashboardlib import (  # noqa: E402
    Dashboard,
    Panel,
    Query,
    dashboard_json,
    panel_json,
    query_target,
)

EXPECTED_DASHBOARDS = {
    "Operations": {"forge-overview"},
    "Curated": {
        "forge-api",
        "forge-async-redis",
        "forge-continuity",
        "forge-logs-changes",
        "forge-postgres-pgbouncer",
        "forge-search",
        "forge-host-containers",
    },
    "Exporters": {
        "forge-node-exporter",
        "forge-cadvisor",
        "forge-postgres-exporter",
        "forge-pgbouncer-exporter",
        "forge-redis-exporter",
        "forge-celery-exporter",
        "forge-nginx-exporter",
        "forge-meilisearch-detail",
        "forge-prometheus-detail",
        "forge-alertmanager-detail",
        "forge-loki-detail",
        "forge-alloy-detail",
    },
}


def _by_uid() -> dict[str, Dashboard]:
    return {dashboard.uid: dashboard for dashboard in DASHBOARDS}


def _generated(uid: str) -> dict[str, Any]:
    (path,) = list(DASHBOARD_ROOT.rglob(f"{uid}.json"))
    return json.loads(path.read_text())  # type: ignore[no-any-return]


# --- dashboardlib units ---


def test_query_target_has_exact_shape_for_range_and_instant_queries() -> None:
    query = Query("up", "{{job}}")
    assert query_target(query, "A") == {
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "editorMode": "code",
        "expr": "up",
        "legendFormat": "{{job}}",
        "queryType": "range",
        "refId": "A",
        "instant": False,
        "range": True,
    }
    stat = query_target(query, "B", panel_kind="stat")
    assert (
        stat["instant"] is True
        and stat["range"] is False
        and stat["queryType"] == "instant"
    )
    table = query_target(query, "C", panel_kind="table")
    assert table["format"] == "table"
    loki_table = query_target(
        Query('{a="b"}', datasource="loki"), "D", panel_kind="table"
    )
    assert loki_table["datasource"] == {"type": "loki", "uid": "loki"}
    assert loki_table["queryType"] == "instant"


def test_query_targets_get_fresh_datasource_objects() -> None:
    first = query_target(Query("up"), "A")
    second = query_target(Query("up"), "A")
    assert first["datasource"] == second["datasource"]
    assert first["datasource"] is not second["datasource"]


def test_panel_json_sets_grid_ids_units_and_deterministic_ref_ids() -> None:
    panel = Panel(
        "Two series",
        (Query("a", "A"), Query("b", "B", unit="s")),
        unit="reqps",
        thresholds=((None, "green"), (1, "red")),
    )
    body = panel_json(panel, panel_id=7, x=12, y=8)
    assert body["gridPos"] == {"h": 8, "w": 12, "x": 12, "y": 8}
    assert body["id"] == 7
    assert [target["refId"] for target in body["targets"]] == ["A", "B"]
    assert body["fieldConfig"]["defaults"]["unit"] == "reqps"
    assert body["fieldConfig"]["defaults"]["thresholds"]["steps"] == [
        {"color": "green", "value": None},
        {"color": "red", "value": 1},
    ]
    assert body["fieldConfig"]["overrides"] == [
        {
            "matcher": {"id": "byFrameRefID", "options": "B"},
            "properties": [{"id": "unit", "value": "s"}],
        }
    ]
    assert body["type"] == "timeseries"
    assert "options" not in body


@pytest.mark.parametrize("kind", ["stat", "gauge"])
def test_stat_and_gauge_panels_get_no_data_options_and_threshold_colors(
    kind: Literal["stat", "gauge"],
) -> None:
    body = panel_json(
        Panel(
            "Value", (Query("up"),), kind=kind, thresholds=((None, "red"), (1, "green"))
        ),
        panel_id=1,
        x=0,
        y=0,
    )
    assert body["options"]["reduceOptions"]["calcs"] == ["lastNotNull"]
    assert body["fieldConfig"]["defaults"]["color"] == {"mode": "thresholds"}
    assert body["fieldConfig"]["defaults"]["noValue"] == "No data"


def test_dashboard_places_panels_on_24_column_rows() -> None:
    dashboard = Dashboard(
        "Curated",
        "forge-test",
        "Test",
        (
            Panel("A", (Query("a"),), width=12),
            Panel("B", (Query("b"),), width=12),
            Panel("C", (Query("c"),), width=8, height=4),
        ),
    )
    positions = [panel["gridPos"] for panel in dashboard_json(dashboard)["panels"]]
    assert positions == [
        {"h": 8, "w": 12, "x": 0, "y": 0},
        {"h": 8, "w": 12, "x": 12, "y": 0},
        {"h": 4, "w": 8, "x": 0, "y": 8},
    ]


def test_dashboard_emits_links_variables_annotations_and_forge_tags() -> None:
    dashboard = Dashboard(
        "Curated",
        "forge-test",
        "Test",
        (Panel("A", (Query("a"),)),),
        links=(("Overview", "/d/forge-overview"),),
        variables=({"name": "job", "type": "query"},),
        annotations=(
            {
                "name": "Deploy",
                "expr": "forge_deployment_timestamp_seconds",
                "tagKeys": "revision",
            },
        ),
    )
    body = dashboard_json(dashboard)
    assert body["tags"] == ["forge", "production"]
    assert (
        body["links"][0]["url"] == "/d/forge-overview"
        and body["links"][0]["keepTime"] is True
    )
    assert body["templating"]["list"] == [{"name": "job", "type": "query"}]
    assert (
        body["annotations"]["list"][0]["expr"] == "forge_deployment_timestamp_seconds"
    )
    assert body["annotations"]["list"][0]["titleFormat"] == "{{revision}} {{reason}}"
    assert body["editable"] is False and body["refresh"] == "30s"


@pytest.mark.parametrize(
    "expression",
    ["up or vector(0)", "up OR on() vector(0)", "up or ignoring(job) vector(0.0)"],
)
def test_dashboard_rejects_zero_filling_queries(expression: str) -> None:
    with pytest.raises(ValueError, match="forbidden or vector"):
        dashboard_json(
            Dashboard(
                "Curated", "forge-test", "Test", (Panel("A", (Query(expression),)),)
            )
        )


def test_dashboard_rejects_invalid_panels() -> None:
    with pytest.raises(ValueError, match="Duplicate panel title"):
        dashboard_json(
            Dashboard(
                "Curated",
                "forge-test",
                "Test",
                (Panel("A", (Query("a"),)), Panel("A", (Query("b"),))),
            )
        )
    with pytest.raises(ValueError, match="cannot mix datasources"):
        dashboard_json(
            Dashboard(
                "Curated",
                "forge-test",
                "Test",
                (Panel("A", (Query("a"), Query("{b}", datasource="loki"))),),
            )
        )
    with pytest.raises(ValueError, match="Logs panels cannot have data links"):
        dashboard_json(
            Dashboard(
                "Curated",
                "forge-test",
                "Test",
                (
                    Panel(
                        "A",
                        (Query("{b}", datasource="loki"),),
                        kind="logs",
                        data_links=(("x", "/d/x"),),
                    ),
                ),
            )
        )
    with pytest.raises(ValueError, match="width must be within"):
        dashboard_json(
            Dashboard(
                "Curated", "forge-test", "Test", (Panel("A", (Query("a"),), width=25),)
            )
        )
    with pytest.raises(ValueError, match="threshold must be finite"):
        dashboard_json(
            Dashboard(
                "Curated",
                "forge-test",
                "Test",
                (Panel("A", (Query("a"),), thresholds=((float("nan"), "red"),)),),
            )
        )


# --- generator ---


def test_rendered_rejects_duplicate_uids_and_unsafe_paths(tmp_path: Path) -> None:
    panel = Panel("A", (Query("a"),))
    with pytest.raises(ValueError, match="Duplicate dashboard UID"):
        build_dashboards.rendered(
            dashboard_root=tmp_path,
            dashboards=(
                Dashboard("Curated", "forge-x", "X", (panel,)),
                Dashboard("Curated", "forge-x", "Y", (panel,)),
            ),
        )
    with pytest.raises(ValueError, match="Invalid dashboard uid"):
        build_dashboards.rendered(
            dashboard_root=tmp_path,
            dashboards=(Dashboard("Curated", "other-x", "X", (panel,)),),
        )
    with pytest.raises(ValueError, match="Invalid dashboard folder"):
        build_dashboards.rendered(
            dashboard_root=tmp_path,
            dashboards=(Dashboard("../escape", "forge-x", "X", (panel,)),),
        )


def test_build_writes_owned_dashboards_and_reports_foreign_json(tmp_path: Path) -> None:
    root = tmp_path / "dashboards"
    root.mkdir()
    stale = root / "Curated" / "forge-stale.json"
    stale.parent.mkdir()
    stale.write_text("{}")
    foreign = root / "Curated" / "manual.json"
    foreign.write_text("{}")
    dashboards = (Dashboard("Curated", "forge-x", "X", (Panel("A", (Query("a"),)),)),)
    assert (
        build_dashboards.run(check=False, dashboard_root=root, dashboards=dashboards)
        == 1
    )
    assert not stale.exists()
    assert foreign.exists()
    assert json.loads((root / "Curated/forge-x.json").read_text())["uid"] == "forge-x"
    foreign.unlink()
    assert (
        build_dashboards.run(check=True, dashboard_root=root, dashboards=dashboards)
        == 0
    )
    (root / "Curated/forge-x.json").write_text("{}")
    assert (
        build_dashboards.run(check=True, dashboard_root=root, dashboards=dashboards)
        == 1
    )


def test_generated_dashboards_are_current() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_dashboards.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- provisioning ---


def test_provisioning_uses_filesystem_folders_and_stable_datasources() -> None:
    providers = yaml.safe_load(
        (DEPLOY / "grafana/provisioning/dashboards/dashboards.yml").read_text()
    )["providers"]
    assert providers == [
        {
            "name": "Forge",
            "orgId": 1,
            "type": "file",
            "disableDeletion": True,
            "editable": False,
            "updateIntervalSeconds": 30,
            "options": {
                "path": "/var/lib/grafana/dashboards",
                "foldersFromFilesStructure": True,
            },
        }
    ]
    datasources = yaml.safe_load(
        (DEPLOY / "grafana/provisioning/datasources/datasources.yml").read_text()
    )["datasources"]
    assert [
        (source["uid"], source["type"], source["url"]) for source in datasources
    ] == [
        ("prometheus", "prometheus", "http://prometheus:9090"),
        ("loki", "loki", "http://loki:3100"),
    ]
    assert all(
        source["editable"] is False and source["jsonData"] == {"timeInterval": "15s"}
        for source in datasources
    )
    for optional in ("alerting", "plugins"):
        assert (DEPLOY / "grafana/provisioning" / optional / ".gitkeep").exists()


# --- dashboard catalogue ---


def test_exact_dashboard_set_is_provisioned_by_folder() -> None:
    by_folder: dict[str, set[str]] = {}
    for dashboard in DASHBOARDS:
        by_folder.setdefault(dashboard.folder, set()).add(dashboard.uid)
    assert by_folder == EXPECTED_DASHBOARDS
    generated = {
        path.parent.name: {path.stem for path in paths}
        for path in DASHBOARD_ROOT.rglob("*.json")
        for paths in [[path]]
    }
    on_disk: dict[str, set[str]] = {}
    for path in DASHBOARD_ROOT.rglob("*.json"):
        on_disk.setdefault(path.parent.name, set()).add(path.stem)
    assert on_disk == EXPECTED_DASHBOARDS
    assert generated


def test_dashboards_use_forge_names_and_no_legacy_rest_panels() -> None:
    text = (SCRIPTS / "dashboard_specs.py").read_text()
    assert "legacy" not in text.lower()
    for dashboard in DASHBOARDS:
        assert dashboard.uid.startswith("forge-")
        assert dashboard.title.startswith("Forge") or dashboard.folder == "Exporters", (
            dashboard.uid
        )


def test_every_dashboard_links_back_to_overview_and_every_uid_link_resolves() -> None:
    uids = set(_by_uid())
    for dashboard in DASHBOARDS:
        if dashboard.uid != "forge-overview":
            assert any(
                url.startswith("/d/forge-overview") for _title, url in dashboard.links
            ), dashboard.uid
        for _title, url in dashboard.links:
            match = re.match(r"/d/(forge-[a-z0-9-]+)", url)
            assert match and match.group(1) in uids, (dashboard.uid, url)
        for panel in dashboard.panels:
            for _title, url in panel.data_links:
                match = re.match(r"/d/(forge-[a-z0-9-]+)", url)
                assert match and match.group(1) in uids, (dashboard.uid, url)


def test_every_variable_is_referenced_by_a_panel_target() -> None:
    for dashboard in DASHBOARDS:
        expressions = " ".join(
            query.expr for panel in dashboard.panels for query in panel.queries
        )
        for variable in dashboard.variables:
            assert f"${variable['name']}" in expressions, (
                dashboard.uid,
                variable["name"],
            )


def test_no_dashboard_query_zero_fills_or_uses_legacy_metrics() -> None:
    for dashboard in DASHBOARDS:
        for panel in dashboard.panels:
            for query in panel.queries:
                assert "vector(0)" not in query.expr, (dashboard.uid, panel.title)
                assert "legacy" not in query.expr.lower(), (dashboard.uid, panel.title)


def test_logs_panels_have_no_data_links_and_are_loki_backed() -> None:
    for dashboard in DASHBOARDS:
        for panel in dashboard.panels:
            if panel.kind == "logs":
                assert panel.data_links == (), (dashboard.uid, panel.title)
                assert all(query.datasource == "loki" for query in panel.queries)


def test_overview_answers_incident_questions_with_forge_metrics() -> None:
    overview = _by_uid()["forge-overview"]
    titles = [panel.title for panel in overview.panels]
    assert titles[:6] == [
        "Public probes",
        "GraphQL outcomes / server faults",
        "API p95 latency",
        "Backup age / transfer state",
        "Firing alerts",
        "Request rate by protocol",
    ]
    assert "GraphQL server-fault rate" in titles
    assert (
        "Dependency quick scan" in titles and "Error logs by Compose service" in titles
    )
    expressions = " ".join(
        query.expr for panel in overview.panels for query in panel.queries
    )
    assert 'up{job=~"forge-web|' in expressions
    assert "forge:api_request_duration_seconds:p95_5m" in expressions
    annotations = {
        annotation["name"]: annotation["expr"] for annotation in overview.annotations
    }
    assert "forge_deployment_timestamp_seconds" in annotations["Deploy revision"]
    assert "forge_maintenance_info" in annotations["Maintenance"]


def test_continuity_and_celery_dashboards_use_producer_metric_names() -> None:
    continuity = " ".join(
        query.expr
        for panel in _by_uid()["forge-continuity"].panels
        for query in panel.queries
    )
    backup_script = (DEPLOY / "backup/backup.sh").read_text()
    for metric in (
        "backup_last_success_timestamp_seconds",
        "backup_last_attempt_success",
        "backup_size_bytes",
        "backup_transfer_last_failure_timestamp_seconds",
    ):
        assert metric in continuity and metric in backup_script
    celery = " ".join(
        query.expr
        for panel in _by_uid()["forge-celery-exporter"].panels
        for query in panel.queries
    )
    assert (
        "forge_celery_queue_depth" in celery
        and "forge_celery_oldest_task_age_seconds" in celery
    )


def test_generated_overview_json_is_deterministic_and_positioned() -> None:
    body = _generated("forge-overview")
    assert body["uid"] == "forge-overview"
    assert body["tags"] == ["forge", "production"]
    ids = [panel["id"] for panel in body["panels"]]
    assert ids == list(range(1, len(ids) + 1))
    for panel in body["panels"]:
        assert set(panel["gridPos"]) == {"h", "w", "x", "y"}
        assert panel["datasource"]["uid"] in {"prometheus", "loki"}
    assert (
        json.dumps(body, sort_keys=True, indent=2) + "\n"
        == list(DASHBOARD_ROOT.rglob("forge-overview.json"))[0].read_text()
    )
