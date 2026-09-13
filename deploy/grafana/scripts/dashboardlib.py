from __future__ import annotations

import math
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

PROMETHEUS = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}

NO_DATA_OPTIONS: dict[str, Any] = {
    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
    "textMode": "auto",
    "wideLayout": True,
}

FIELD_DEFAULTS: dict[str, Any] = {
    "color": {"mode": "palette-classic"},
    "mappings": [],
    "noValue": "No data",
    "thresholds": {
        "mode": "absolute",
        "steps": [{"color": "green", "value": None}],
    },
}

PANEL_KINDS = {"timeseries", "stat", "gauge", "table", "logs"}
DATASOURCES = {"prometheus", "loki"}
ZERO_FILL = re.compile(
    r"\bor\b(?:\s+(?:on|ignoring)\s*\([^)]*\))?"
    r"\s+vector\s*\(\s*0(?:\.0*)?\s*\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Query:
    expr: str
    legend: str = ""
    datasource: Literal["prometheus", "loki"] = "prometheus"
    unit: str | None = None
    thresholds: tuple[tuple[float | None, str], ...] | None = None


@dataclass(frozen=True)
class Panel:
    title: str
    queries: tuple[Query, ...]
    kind: Literal["timeseries", "stat", "gauge", "table", "logs"] = "timeseries"
    unit: str = "short"
    description: str = ""
    width: int = 12
    height: int = 8
    time_from: str | None = None
    thresholds: tuple[tuple[float | None, str], ...] = ()
    data_links: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Dashboard:
    folder: str
    uid: str
    title: str
    panels: tuple[Panel, ...]
    links: tuple[tuple[str, str], ...] = ()
    variables: tuple[dict[str, Any], ...] = ()
    annotations: tuple[dict[str, Any], ...] = ()
    default_from: str = "now-6h"
    tags: tuple[str, ...] = field(default=("forge", "production"))


def query_target(
    query: Query,
    ref_id: str,
    *,
    panel_kind: str = "timeseries",
) -> dict[str, Any]:
    if query.datasource not in DATASOURCES:
        raise ValueError(f"Invalid datasource: {query.datasource}")
    datasource = deepcopy(PROMETHEUS if query.datasource == "prometheus" else LOKI)
    target: dict[str, Any] = {
        "datasource": datasource,
        "editorMode": "code",
        "expr": query.expr,
        "legendFormat": query.legend,
        "queryType": "range",
        "refId": ref_id,
    }
    if query.datasource == "prometheus":
        instant = panel_kind in {"stat", "gauge", "table"}
        target.update(
            {
                "instant": instant,
                "queryType": "instant" if instant else "range",
                "range": not instant,
            }
        )
        if panel_kind == "table":
            target["format"] = "table"
    elif panel_kind == "table":
        target["queryType"] = "instant"
    return target


def dashboard_link(title: str, url: str) -> dict[str, Any]:
    return {
        "asDropdown": False,
        "icon": "external link",
        "includeVars": True,
        "keepTime": True,
        "tags": [],
        "targetBlank": False,
        "title": title,
        "tooltip": "",
        "type": "link",
        "url": url,
    }


def annotation(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "datasource": deepcopy(PROMETHEUS),
        "enable": True,
        "expr": deepcopy(source["expr"]),
        "hide": False,
        "iconColor": "blue",
        "name": deepcopy(source["name"]),
        "tagKeys": deepcopy(source.get("tagKeys", "")),
        "titleFormat": "{{revision}} {{reason}}",
    }


def _ref_id(index: int) -> str:
    result = ""
    while True:
        index, remainder = divmod(index, 26)
        result = chr(ord("A") + remainder) + result
        if index == 0:
            return result
        index -= 1


def _validate_thresholds(
    thresholds: tuple[tuple[float | None, str], ...],
    *,
    subject: str,
) -> None:
    for value, _color in thresholds:
        if value is None:
            continue
        try:
            finite = math.isfinite(value)
        except TypeError as error:
            raise ValueError(f"threshold must be finite: {subject}") from error
        if not finite:
            raise ValueError(f"threshold must be finite: {subject}")


def _threshold_config(
    thresholds: tuple[tuple[float | None, str], ...],
) -> dict[str, Any]:
    return {
        "mode": "absolute",
        "steps": [{"color": color, "value": value} for value, color in thresholds],
    }


def _query_override(query: Query, ref_id: str) -> dict[str, Any] | None:
    properties: list[dict[str, Any]] = []
    if query.unit is not None:
        properties.append({"id": "unit", "value": query.unit})
    if query.thresholds is not None:
        properties.append(
            {"id": "thresholds", "value": _threshold_config(query.thresholds)}
        )
    if not properties:
        return None
    return {
        "matcher": {"id": "byFrameRefID", "options": ref_id},
        "properties": properties,
    }


def _validate_panel(panel: Panel) -> None:
    if not 1 <= panel.width <= 24:
        raise ValueError(f"Panel width must be within 1..24: {panel.title}")
    if panel.height <= 0:
        raise ValueError(f"Panel height must be positive: {panel.title}")
    if panel.kind not in PANEL_KINDS:
        raise ValueError(f"Invalid panel kind: {panel.kind}")
    if any(query.datasource not in DATASOURCES for query in panel.queries):
        raise ValueError(f"Invalid datasource in panel: {panel.title}")
    if any(ZERO_FILL.search(query.expr) for query in panel.queries):
        raise ValueError(f"Query contains forbidden or vector(0): {panel.title}")
    if panel.kind == "logs" and panel.data_links:
        raise ValueError(f"Logs panels cannot have data links: {panel.title}")
    _validate_thresholds(panel.thresholds, subject=panel.title)
    for query in panel.queries:
        if query.thresholds is not None:
            _validate_thresholds(
                query.thresholds,
                subject=f"{panel.title} query {query.legend or query.expr}",
            )
    datasources = {query.datasource for query in panel.queries}
    if len(datasources) > 1:
        raise ValueError(f"Panel cannot mix datasources: {panel.title}")


def panel_json(panel: Panel, *, panel_id: int, x: int, y: int) -> dict[str, Any]:
    _validate_panel(panel)
    if not panel.queries:
        raise ValueError(f"Panel must have at least one query: {panel.title}")

    defaults = deepcopy(FIELD_DEFAULTS)
    defaults["unit"] = panel.unit
    if panel.thresholds:
        defaults["thresholds"] = _threshold_config(panel.thresholds)
    if panel.data_links:
        defaults["links"] = [
            {"title": title, "url": url} for title, url in panel.data_links
        ]
    threshold_driven = panel.thresholds or any(
        query.thresholds is not None for query in panel.queries
    )
    if panel.kind in {"stat", "gauge"} and threshold_driven:
        defaults["color"] = {"mode": "thresholds"}

    overrides = [
        override
        for index, query in enumerate(panel.queries)
        if (override := _query_override(query, _ref_id(index))) is not None
    ]

    datasource = deepcopy(
        PROMETHEUS if panel.queries[0].datasource == "prometheus" else LOKI
    )
    body = {
        "datasource": datasource,
        "description": panel.description,
        "fieldConfig": {"defaults": defaults, "overrides": overrides},
        "gridPos": {"h": panel.height, "w": panel.width, "x": x, "y": y},
        "id": panel_id,
        "targets": [
            query_target(query, _ref_id(index), panel_kind=panel.kind)
            for index, query in enumerate(panel.queries)
        ],
        "title": panel.title,
        "type": panel.kind,
    }
    if panel.kind in {"stat", "gauge"}:
        body["options"] = deepcopy(NO_DATA_OPTIONS)
    if panel.time_from is not None:
        body["timeFrom"] = panel.time_from
    return body


def _validate_dashboard(dashboard: Dashboard) -> None:
    titles: set[str] = set()
    for panel in dashboard.panels:
        if panel.title in titles:
            raise ValueError(f"Duplicate panel title: {panel.title}")
        titles.add(panel.title)
        _validate_panel(panel)


def dashboard_json(dashboard: Dashboard) -> dict[str, Any]:
    _validate_dashboard(dashboard)
    panels: list[dict[str, Any]] = []
    x = 0
    y = 0
    row_height = 0
    for panel_id, panel in enumerate(dashboard.panels, start=1):
        if x + panel.width > 24:
            x = 0
            y += row_height
            row_height = 0
        panels.append(panel_json(panel, panel_id=panel_id, x=x, y=y))
        x += panel.width
        row_height = max(row_height, panel.height)

    return {
        "annotations": {
            "list": [annotation(source) for source in dashboard.annotations]
        },
        "editable": False,
        "links": [dashboard_link(title, url) for title, url in dashboard.links],
        "panels": panels,
        "refresh": "30s",
        "schemaVersion": 41,
        "tags": list(dashboard.tags),
        "templating": {"list": deepcopy(list(dashboard.variables))},
        "time": {"from": dashboard.default_from, "to": "now"},
        "timezone": "browser",
        "title": dashboard.title,
        "uid": dashboard.uid,
        "version": 1,
    }
