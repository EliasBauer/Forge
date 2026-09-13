# Deploy-Setup nach dem Muster eines ähnlichen Projekts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Forge bekommt einen `deploy/`-Ordner mit demselben Single-Host-Docker-Compose-Aufbau wie `<Referenzprojekt>/deploy` (Kern, Observability, Administration, Backup/Restore-Verification, Maintenance-System), zwei Daphne-Instanzen, und wird auf `<operator>@<testserver>` verifiziert.

**Architecture:** Ein Compose-Projekt `forge` mit Profilen `deployment`, `observability`, `administration`, `backup`, `restore-verification`; nginx als einziger Host-Port mit drei TLS-Virtual-Hosts; Secrets als Dateien; Backend liest `*_FILE`-Secrets, liefert Health-Endpoints, Prometheus-Metriken (django-prometheus + GM-GraphQL-Metriken + eigene API-/Queue-Metriken) und JSON-Logs. Skripte, Prometheus-Regeln, Alertmanager-Template, Grafana-Dashboard-Generator und Runbook werden aus das Referenzprojekt portiert und umbenannt.

**Tech Stack:** Django 6 / GeneralManager 0.79.3 / Celery 5.6 / Channels 4.3 (Backend), Vite/React (Frontend), Docker Compose v2, nginx (Debian trixie), PostgreSQL 17, pgBouncer, Redis 7, Meilisearch 1.45, Prometheus 3.12, Alertmanager 0.33, Grafana 13, Loki 3.7, Alloy 1.17, Exporter wie das Referenzprojekt.

**Spec:** `docs/superpowers/specs/2026-09-13-deploy-docker-compose-design.md`
**Referenz-Implementierung:** `<lokaler Checkout des Referenzprojekts>/deploy` (lokal, lesbar). Wo der Plan "Quelle: das Referenzprojekt …" sagt, wird die Datei kopiert und exakt mit den genannten Änderungen angepasst; alles andere bleibt byte-identisch.

## Global Constraints

- Branch `implement_deploy`; jeder Task-Commit nimmt diese Plan-Datei mit auf (`git add docs/superpowers/plans/2026-09-13-deploy-docker-compose.md`).
- Alle Dev-Befehle laufen im Devcontainer: `devcontainer exec --workspace-folder . <cmd>`. Commits ebenfalls dort, mit `PATH=$PWD/.venv/bin:$PATH`, damit der pre-commit-Hook `pre-commit` findet. Niemals `--no-verify`.
- Commit-Identität: `git -c user.name=EliasBauer -c user.email=el-bauer@web.de commit …`; Commit-Body endet mit `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Gate vor jedem Commit: `uv run pre-commit run --all-files` grün (ruff check+format, pytest mit 100 % Coverage auf `src`, mypy strict auf `src tests deploy`, vitest).
- Namensschema aus der Spec (Tabelle "Namensschema") gilt für jede portierte Datei: `referenz`→`forge`, `Referenz`→`Forge`, `Referenzprojekt`→`Forge`, `referenz-`→`forge-`, `referenz_`→`forge_`, `/run/referenz`→`/run/forge`, `/srv/referenz`→`/srv/forge/data`, `/etc/referenz`→`/etc/forge`, `referenz-deploy`→`forge-deploy`, `settings.prod`→`forge.settings`, `settings.asgi`→`forge.asgi`, `-A settings`→`-A forge`.
- Nicht portieren (Spec "Nicht-Ziele"): Wiki, Legacy-Cache-Redis, PRO.FILE, MS-SSO, O/Z-Laufwerke, Exports, Templates, `celery-priority`, `celery-automation`, Corporate-CA, GitHub-Token-Build-Secret.
- Images: exakt die in der Spec gepinnten Tags; Celery-Exporter von `ghcr.io/danihodovic/celery-exporter:0.12.2`.
- `web` Default-Replikate: 2 (`WEB_REPLICAS`), `celery-worker` Default 1 (`CELERY_REPLICAS`), Concurrency `CELERY_CONCURRENCY` Default 2.
- Coverage-Pflicht 100 % auf `src` bleibt; jede neue Backend-Datei bekommt Tests.

---

## Datei-Übersicht

Backend (neu/geändert):
- `src/forge/env.py` — Umgebungs-Helfer (`env_bool`, `env_csv`, `env_int`, `env_secret`)
- `src/forge/settings.py` — Prod-Block (DB, Secrets, Security, Logging, Celery, GM-Metriken, Middleware)
- `src/forge/health.py`, `src/forge/urls.py` — `/health/*`, `/metrics`
- `src/forge/asgi.py` — WebSocket-Route
- `src/forge/celery.py` — Autodiscover für `forge.observability`
- `src/forge/graphql_metric_operations.py` — Allowlist der Frontend-Operationen
- `src/forge/observability/{__init__,api_metrics,graphql_probe,middleware,metrics_host,celery_queue_metrics,tasks}.py`
- `tests/test_env.py`, `tests/test_health.py`, `tests/test_asgi.py`, `tests/test_observability_metrics.py`, `tests/test_celery_queue_metrics.py`, `tests/test_celery_config.py`
- `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml`, `.gitignore`, `.dockerignore`

Deploy (neu): siehe Spec-Abschnitt "Skripte", "Observability", "Images"; alle Pfade unter `deploy/`.

Gelöscht: `docker/`, `nginx/`, `frontend/Dockerfile`, `frontend/nginx.conf`, `.env.example`.

Docs: `README.md`, `docs/architektur.md`, `docs/start_dev.md`, `docs/adr/006-deploy-docker-compose.md`, `deploy/README.md`.

---

### Task 1: Umgebungs-Helfer, Abhängigkeiten, Prod-Settings

**Files:**
- Create: `src/forge/env.py`
- Create: `tests/test_env.py`
- Modify: `src/forge/settings.py`
- Modify: `pyproject.toml`, `uv.lock` (per `uv lock`), `.pre-commit-config.yaml` (mypy-Hook)

**Interfaces:**
- Produces: `forge.env.env_bool(name, default=False) -> bool`, `env_csv(name, default="") -> list[str]`, `env_int(name, default) -> int`, `env_secret(name, *, default=None, required=False) -> str`; Settings-Namen `IS_DEV`, `INTERNAL_METRICS_HOST`, `MAINTENANCE_FLAG_FILE`, `PUSHGATEWAY_URL`, `LOG_TO_STDOUT`.

- [x] **Step 1: Failing tests für `env.py`**

`tests/test_env.py`:

```python
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from forge.env import env_bool, env_csv, env_int, env_secret


def test_env_bool_parses_truthy_and_falsy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAG", " Yes ")
    assert env_bool("FLAG") is True
    monkeypatch.setenv("FLAG", "off")
    assert env_bool("FLAG") is False
    monkeypatch.delenv("FLAG")
    assert env_bool("FLAG", True) is True


def test_env_bool_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAG", "maybe")
    with pytest.raises(ValueError, match="FLAG"):
        env_bool("FLAG")


def test_env_csv_strips_and_drops_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOSTS", " a.example , ,b.example")
    assert env_csv("HOSTS") == ["a.example", "b.example"]
    monkeypatch.delenv("HOSTS")
    assert env_csv("HOSTS", "x,y") == ["x", "y"]


def test_env_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("N", "7")
    assert env_int("N", 1) == 7
    monkeypatch.delenv("N")
    assert env_int("N", 1) == 1
    monkeypatch.setenv("N", "x")
    with pytest.raises(ValueError, match="N"):
        env_int("N", 1)


def test_env_secret_prefers_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret = tmp_path / "s.txt"
    secret.write_text("from-file\n")
    monkeypatch.setenv("KEY", "from-env")
    monkeypatch.setenv("KEY_FILE", str(secret))
    assert env_secret("KEY") == "from-file"
    monkeypatch.delenv("KEY_FILE")
    assert env_secret("KEY") == "from-env"
    monkeypatch.delenv("KEY")
    assert env_secret("KEY", default="d") == "d"
    assert env_secret("KEY") == ""


def test_env_secret_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEY", raising=False)
    with pytest.raises(ImproperlyConfigured, match="KEY oder KEY_FILE"):
        env_secret("KEY", required=True)
```

- [x] **Step 2: Test läuft rot**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest tests/test_env.py -q --no-cov`
Expected: `ModuleNotFoundError: No module named 'forge.env'`

- [x] **Step 3: `src/forge/env.py` schreiben**

```python
"""Umgebungs-Helfer für Settings: Docker-Secrets (`NAME_FILE`) vor `NAME`."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ValueError(f"{name} muss ein boolescher Wert sein")


def env_csv(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} muss eine ganze Zahl sein") from exc


def env_secret(name: str, *, default: str | None = None, required: bool = False) -> str:
    file_name = os.environ.get(f"{name}_FILE")
    if file_name:
        value: str | None = Path(file_name).read_text().strip()
    else:
        value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"{name} oder {name}_FILE muss gesetzt sein")
    return value or ""
```

- [x] **Step 4: Tests grün**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest tests/test_env.py -q --no-cov`
Expected: 6 passed

- [x] **Step 5: Abhängigkeiten**

`pyproject.toml` `dependencies`: `dj-database-url>=2.0` entfernen; hinzufügen `django-prometheus>=2.4,<3`, `prometheus-client>=0.23,<1`, `python-json-logger>=3,<4`, `redis>=5`. Dev-Gruppe: `pyyaml>=6`. `[tool.pytest.ini_options] testpaths = ["tests", "src/apps", "deploy/tests"]`. `.pre-commit-config.yaml` mypy-Entry: `uv run --group dev mypy src tests deploy`.

Run: `devcontainer exec --workspace-folder . uv lock && devcontainer exec --workspace-folder . uv sync --group dev`
Expected: Lock aktualisiert, Sync ohne Fehler. Prüfen: `devcontainer exec --workspace-folder . uv run python -c "import django_prometheus, prometheus_client, pythonjsonlogger, redis, yaml"`.

- [x] **Step 6: `settings.py` umbauen**

Vollständige neue Fassung (ersetzt die Datei; Reihenfolge und Werte exakt so):

```python
import os
from pathlib import Path
from typing import Any

from forge.env import env_bool, env_csv, env_int, env_secret
from forge.graphql_metric_operations import GRAPHQL_METRIC_OPERATION_ALLOWLIST

BASE_DIR = Path(__file__).resolve().parent.parent

FORGE_ENV = os.environ.get("FORGE_ENV", "production")
IS_DEV = FORGE_ENV == "dev"

SECRET_KEY = env_secret(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-only-change-in-production" if IS_DEV else None,
    required=not IS_DEV,
)

BEXIO_ACCESS_TOKEN = env_secret("BEXIO_ACCESS_TOKEN") or None
# Im Dev-Modus werden Fixture-Daten statt echter Bexio-API genutzt
BEXIO_DEV_MODE = not bool(BEXIO_ACCESS_TOKEN)

DEBUG = IS_DEV

ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_csv("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")
# Host-Name, unter dem Prometheus /metrics scrapt (siehe forge.observability.metrics_host)
INTERNAL_METRICS_HOST = os.environ.get("INTERNAL_METRICS_HOST", "")
MAINTENANCE_FLAG_FILE = os.environ.get("MAINTENANCE_FLAG_FILE", "/run/forge/maintenance")
PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "")
LOG_TO_STDOUT = env_bool("LOG_TO_STDOUT", not IS_DEV)

INSTALLED_APPS = [
    "daphne",
    "channels",
    "django_prometheus",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.stunden",
    "apps.projekt",
    "apps.authentication",
    "apps.bexio",
    "graphene_django",
    "general_manager",
]

MIDDLEWARE = [
    "forge.observability.metrics_host.InternalMetricsHostMiddleware",
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "forge.observability.middleware.ApiMetricsMiddleware",
    "forge.middleware.DisableCSRFForGraphQL",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "forge.urls"
WSGI_APPLICATION = "forge.wsgi.application"
ASGI_APPLICATION = "forge.asgi.application"

TEMPLATES = [  # unverändert
    ...
]

# --- Database ---
if IS_DEV:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django_prometheus.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "forge"),
            "USER": os.environ.get("POSTGRES_USER", "forge"),
            "PASSWORD": env_secret("POSTGRES_PASSWORD", required=True),
            "HOST": os.environ.get("POSTGRES_HOST", "pgbouncer"),
            "PORT": env_int("POSTGRES_PORT", 5432),
            # 0 = pro Request neue Verbindung (empfohlen hinter pgBouncer)
            "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 0),
            "CONN_HEALTH_CHECKS": True,
            # Pflicht für pgBouncer Transaction-Pooling
            "DISABLE_SERVER_SIDE_CURSORS": True,
            "OPTIONS": {"connect_timeout": env_int("POSTGRES_CONNECT_TIMEOUT", 5)},
        }
    }

# --- Cache & Channels --- (unverändert: REDIS_URL-Schalter, ADR 003)

# --- Static files ---
STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", BASE_DIR / "staticfiles"))

# --- Celery ---
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = env_int("CELERY_WORKER_PREFETCH_MULTIPLIER", 1)
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 1800)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 1680)
# Pflicht für den Celery-Exporter (Task-Events)
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True

CELERY_BEAT_SCHEDULE = {
    "bexio-sync-weekly": {...},  # unverändert
}
if not IS_DEV:
    CELERY_BEAT_SCHEDULE["publish-observability-queue-metrics"] = {
        "task": "forge.observability.tasks.publish_observability_queue_metrics",
        "schedule": 60.0,
    }

# --- Suche --- (MEILISEARCH_URL unverändert; api_key: env_secret("MEILISEARCH_MASTER_KEY") or None)

GENERAL_MANAGER = {
    ... bestehende Keys ...,
    "GRAPHQL_METRICS_ENABLED": not IS_DEV,
    "GRAPHQL_METRICS_BACKEND": "prometheus",
    "GRAPHQL_METRICS_OPERATION_ALLOWLIST": list(GRAPHQL_METRIC_OPERATION_ALLOWLIST),
    "GRAPHQL_METRICS_UNKNOWN_OPERATION_POLICY": "unknown",
    "GRAPHQL_METRICS_RESOLVER_TIMING": False,
}

# --- Produktion hinter nginx (TLS-Terminierung) ---
if not IS_DEV:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^health/", r"^metrics/?$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # 0 = kein HSTS (selbstsignierte Zertifikate); mit vertrauenswürdigem Zertifikat 31536000 setzen
    SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = False

if LOG_TO_STDOUT:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
        "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    }
```

`forge/graphql_metric_operations.py` (in Task 3 mit Tests; hier bereits anlegen, sonst importiert `settings.py` ins Leere):

```python
"""Operationsnamen des Frontends; alles andere wird als `unknown` gezählt."""

GRAPHQL_METRIC_OPERATION_ALLOWLIST = (
    "CreateKostenPosition",
    "CreateProjekt",
    "CreateStundensatz",
    "DeleteKostenPosition",
    "DeleteStundensatz",
    "FehlendeStundensatzJahre",
    "KostenartIds",
    "Me",
    "ProjektDetail",
    "ProjektListe",
    "ProjektListeUpdated",
    "ProjektStatusIds",
    "ProjektUpdated",
    "Projektleiter",
    "SearchProjekte",
    "StundensaetzeListe",
    "UpdateKostenPosition",
    "UpdateProjekt",
    "UpdateStundensatz",
)
```

Die Middleware-Module aus Task 3 existieren noch nicht: in Task 1 die beiden `forge.observability.*`-Einträge in `MIDDLEWARE` noch auskommentiert lassen und in Task 3 aktivieren.

- [x] **Step 7: Gate**

Run: `devcontainer exec --workspace-folder . uv run pre-commit run --all-files`
Expected: alle Hooks grün (pytest inkl. 100 % Coverage; `settings.py` ist coverage-omitted).

- [x] **Step 8: Commit**

```bash
devcontainer exec --workspace-folder . sh -c 'export PATH=$PWD/.venv/bin:$PATH; git add src/forge/env.py src/forge/settings.py src/forge/graphql_metric_operations.py tests/test_env.py pyproject.toml uv.lock .pre-commit-config.yaml docs/superpowers/plans/2026-09-13-deploy-docker-compose.md docs/superpowers/specs/2026-09-13-deploy-docker-compose-design.md && git -c user.name=EliasBauer -c user.email=el-bauer@web.de commit -m "feat(settings): Prod-Settings mit Datei-Secrets, Prometheus-DB-Backend und JSON-Logs" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"'
```

---

### Task 2: Health-Endpoints, `/metrics`, WebSocket-Route

**Files:**
- Create: `src/forge/health.py`, `tests/test_health.py`, `tests/test_asgi.py`
- Modify: `src/forge/urls.py`, `src/forge/asgi.py`

**Interfaces:**
- Produces: Views `forge.health.live`, `ready`, `maintenance`; URLs `/health/live/`, `/health/ready/`, `/health/maintenance/`, `/metrics`; ASGI `application` mit `websocket`-Mapping.

- [x] **Step 1: Failing tests**

`tests/test_health.py`:

```python
from pathlib import Path

import pytest
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


def test_live_needs_no_dependencies() -> None:
    response = Client().get("/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_database_and_cache() -> None:
    response = Client().get("/health/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}


def test_ready_reports_database_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from forge import health

    def broken() -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(health, "_check_database", broken)
    response = Client().get("/health/ready/")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "error"


def test_ready_reports_cache_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from forge import health

    def broken() -> None:
        raise RuntimeError("cache down")

    monkeypatch.setattr(health, "_check_cache", broken)
    response = Client().get("/health/ready/")
    assert response.status_code == 503
    assert response.json()["checks"]["cache"] == "error"


def test_maintenance_reflects_flag_file(tmp_path: Path) -> None:
    flag = tmp_path / "maintenance"
    with override_settings(MAINTENANCE_FLAG_FILE=str(flag)):
        assert Client().get("/health/maintenance/").status_code == 200
        flag.write_text("maintenance")
        response = Client().get("/health/maintenance/")
    assert response.status_code == 503
    assert response.json() == {"maintenance": True}


def test_metrics_endpoint_is_exposed() -> None:
    response = Client().get("/metrics")
    assert response.status_code == 200
    assert b"django_http_requests_total" in response.content
```

`tests/test_asgi.py`:

```python
import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from forge.asgi import application


@pytest.mark.django_db
def test_graphql_websocket_route_accepts_graphql_transport_ws() -> None:
    async def connect() -> tuple[bool, str | None]:
        communicator = WebsocketCommunicator(
            application, "/graphql/", subprotocols=["graphql-transport-ws"]
        )
        connected, subprotocol = await communicator.connect()
        await communicator.disconnect()
        return connected, subprotocol

    connected, subprotocol = async_to_sync(connect)()
    assert connected is True
    assert subprotocol == "graphql-transport-ws"
```

- [x] **Step 2: Rot laufen lassen** — `pytest tests/test_health.py tests/test_asgi.py -q --no-cov` → 404 bzw. Verbindung abgelehnt.

- [x] **Step 3: Implementieren**

`src/forge/health.py`:

```python
"""Liveness/Readiness für Docker-Healthchecks, deploy.sh und Blackbox-Probes."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse


def _check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def _check_cache() -> None:
    cache.set("forge-readiness", "ok", timeout=5)
    if cache.get("forge-readiness") != "ok":
        raise RuntimeError("cache roundtrip failed")


def _outcome(check: object) -> str:
    try:
        check()  # type: ignore[operator]
        return "ok"
    except Exception:  # noqa: BLE001 - jede Störung ist "nicht bereit"
        return "error"


def live(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def ready(_request: HttpRequest) -> JsonResponse:
    checks = {"database": _outcome(_check_database), "cache": _outcome(_check_cache)}
    healthy = all(value == "ok" for value in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "error", "checks": checks},
        status=200 if healthy else 503,
    )


def maintenance(_request: HttpRequest) -> JsonResponse:
    enabled = Path(settings.MAINTENANCE_FLAG_FILE).exists()
    return JsonResponse({"maintenance": enabled}, status=503 if enabled else 200)
```

(`_outcome` mit `Callable[[], None]` typisieren statt `object`; das `type: ignore` entfällt dann.)

`src/forge/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path

from forge import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.authentication.urls")),
    path("health/live/", health.live, name="health-live"),
    path("health/ready/", health.ready, name="health-ready"),
    path("health/maintenance/", health.maintenance, name="health-maintenance"),
    path("", include("django_prometheus.urls")),
]
```

`src/forge/asgi.py`:

```python
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "forge.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.urls import re_path  # noqa: E402
from general_manager.api.graphql_subscription_consumer import (  # noqa: E402
    GraphQLSubscriptionConsumer,
)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter([re_path(r"^graphql/?$", GraphQLSubscriptionConsumer.as_asgi())])
        ),
    }
)
```

- [x] **Step 4: Grün + Gate + Commit** — `feat(backend): Health-Endpoints, /metrics und WebSocket-Route für Subscriptions`

---

### Task 3: Observability-Paket im Backend

**Files:**
- Create: `src/forge/observability/__init__.py`, `api_metrics.py`, `graphql_probe.py`, `middleware.py`, `metrics_host.py`, `celery_queue_metrics.py`, `tasks.py`
- Create: `tests/test_observability_metrics.py`, `tests/test_celery_queue_metrics.py`, `tests/test_celery_config.py`
- Modify: `src/forge/settings.py` (Middleware-Einträge aktivieren), `src/forge/celery.py`

**Interfaces:**
- Produces: `classify_api_request(request) -> tuple[str, str] | None` (`("graphql","graphql")` oder `("auth", "login"|"logout"|"other")`), `record_api_response(classification, *, method, status, duration_seconds)`, Counter `forge_api_requests_total`, Histogram `forge_api_request_duration_seconds`; `is_synthetic_graphql_health_probe(request)`; `ApiMetricsMiddleware`; `InternalMetricsHostMiddleware` + `_is_ip_host`; `collect_queue_metrics(redis_client, *, now=None) -> str` mit `QUEUES = ("default", "search.reconciliation")`, Header `forge_published_at`, `publish_observability_queue_metrics()` (Pushgateway-Job `forge_celery_queues`); Task-Name `forge.observability.tasks.publish_observability_queue_metrics`.

Quelle: `<Referenzprojekt>/backend/utils/observability/{api_metrics,graphql_probe,middleware,metrics_host,celery_queue_metrics}.py`. Änderungen:
- `api_metrics.py`: `ApiName = Literal["graphql", "auth"]`; statt `_LEGACY_PREFIX` → `_AUTH_PREFIX = "/api/"`, Endpoint-Gruppe = zweites Pfadsegment (`login`, `logout`), sonst `other`; Metriknamen `forge_api_requests_total`, `forge_api_request_duration_seconds`, Doku-Strings "Forge API …".
- `celery_queue_metrics.py`: `QUEUES = ("default", "search.reconciliation")`, `_PUBLISHED_AT_HEADER = "forge_published_at"`, `_PUSH_JOB = "forge_celery_queues"`, `dispatch_uid="forge.observability.celery_queue_metrics.publish_timestamp"`, Metriknamen `forge_celery_queue_depth`, `forge_celery_oldest_task_age_seconds`.
- `tasks.py`: `@shared_task(name="forge.observability.tasks.publish_observability_queue_metrics") def publish_observability_queue_metrics() -> None: publish_queue_metrics()`.
- `celery.py`: nach `app.autodiscover_tasks()` zusätzlich `app.autodiscover_tasks(["forge.observability"])`.
- `settings.py`: die beiden auskommentierten Middleware-Zeilen aktivieren.

Tests: Port der relevanten Fälle aus `<Referenzprojekt>/backend/tests/test_observability_metrics.py` (Klassifikation, Probe-Lookalikes, Middleware sync/async/Redirect, Counter-Inkrement, Metrics-Host-Grammatik inkl. IP-Host-Akzeptanz auf `/metrics` und Ablehnung sonst) und `tests/test_celery.py` (Queue-Depth/Age, ungültige Nachrichten, Clamp, Best-Effort-Publish per `monkeypatch` auf `redis.Redis.from_url` und `requests.put`), plus `test_graphql_metric_allowlist_includes_frontend_source` (Regex-Scan über `frontend/src/**/*.ts(x)` ohne Tests) und `tests/test_celery_config.py` (Beat-Eintrag in Prod, Events-Flags, Default-Queue, Task registriert unter dem erwarteten Namen). Jede Zeile der neuen Module muss von Tests erreicht werden (Coverage 100 %).

- [x] Tests rot → Module → grün → Gate → Commit `feat(observability): API-/Queue-Metriken, Metrics-Host-Adapter, Probe-Erkennung`

---

### Task 4: Repo-Aufräumen, Ignore-Dateien, Docs

**Files:**
- Delete: `docker/Dockerfile`, `docker/docker-compose.yml`, `frontend/Dockerfile`, `frontend/nginx.conf`, `nginx/nginx.conf`, `.env.example`
- Create: `.dockerignore`, `docs/adr/006-deploy-docker-compose.md`
- Modify: `.gitignore`, `README.md`, `docs/architektur.md`, `docs/start_dev.md`

- [x] `.dockerignore` (Root):

```
.git
**/.env
**/.env.*
deploy/.env
deploy/.env.*
deploy/secrets/*.txt
**/node_modules
frontend/dist
.venv
**/__pycache__
**/.pytest_cache
.mypy_cache
.ruff_cache
htmlcov
*.sqlite3
staticfiles
.claude
docs
```

- [x] `.gitignore` ergänzen: `deploy/.env`, `deploy/.env.*`, `deploy/secrets/*.txt`, `deploy/tests/__pycache__/`; die Einträge `postgres-data/`, `meilisearch-data/` entfernen.
- [x] README: Setup-Schritt 4 (`cp .env.example`) streichen (Dev braucht keine `.env`, `FORGE_ENV=dev` kommt aus dem Devcontainer); Abschnitt "Deployment" ersetzen durch Verweis auf `deploy/README.md` (Kurzform: Voraussetzungen, `validate-config.sh`, `deploy.sh`, `start-ops.sh`); Tech-Stack-Tabelle (Postgres 17, GM 0.79). `docs/architektur.md`: Verzeichnisstruktur (`deploy/` statt `docker/`+`nginx/`), Settings-Tabelle (`POSTGRES_*`, `*_FILE`, `CSRF_TRUSTED_ORIGINS`, `INTERNAL_METRICS_HOST`), Deployment-Tabelle = Spec-Service-Tabelle. `docs/start_dev.md`: "Schnellstart mit Docker" → Verweis auf `deploy/README.md`; Env-Tabelle korrigieren. ADR 006 (Kontext, Entscheidung: Single-Host Compose nach dem Muster eines ähnlichen Projekts, Konsequenzen, verworfene Alternativen: k3s, systemd-Units, Cloud).
- [x] Gate → Commit `chore: alte Deploy-Reste entfernen, dockerignore, Docs und ADR 006`

---

### Task 5: Compose, Images, nginx, Secrets, `.env.example` + Contract-Tests

**Files:**
- Create: `deploy/compose.yml`, `deploy/.env.example`, `deploy/.gitignore` (`*__pycache__`), `deploy/backend/Dockerfile`, `deploy/backend/entrypoint.sh`, `deploy/nginx/Dockerfile`, `deploy/nginx/entrypoint.sh`, `deploy/nginx/nginx.conf.template`, `deploy/nginx/maintenance.html`, `deploy/pgbouncer/entrypoint.sh`, `deploy/pgbouncer-exporter/entrypoint.sh`, `deploy/pgadmin/servers.json`, `deploy/secrets/{django_secret_key,postgres_password,meilisearch_api_key,bexio_access_token,admin_htpasswd,grafana_admin_password,pgadmin_password,teams_workflow_url,smtp_password}.txt.example`
- Create: `deploy/tests/__init__.py`, `deploy/tests/test_compose_contract.py`, `deploy/tests/test_nginx_contract.py`, `deploy/tests/test_image_contract.py`

Quelle: `<Referenzprojekt>/deploy/compose.yml`. Änderungen gegenüber der Quelle:
- Services `wiki-db`, `wiki`, `wiki-backup`, `wiki-restore-postgres`, `wiki-restore-verify`, `legacy-response-redis`, `legacy-response-redis-exporter`, `celery-priority`, `celery-automation` entfallen; Netze `wiki-data`, `wiki-restore-verification`, Volume `wiki_restore_postgres_data`, Secrets `github_token`, `ms_app_secret`, `ms_backend_secret`, `profile_password`, `profile_bridge_api_token`, `wiki_postgres_password` entfallen; Secret `bexio_access_token` (Datei `./secrets/bexio_access_token.txt`) kommt hinzu.
- `x-backend-environment` exakt wie Spec "Backend-Umgebung"; `x-backend-secrets`: `django_secret_key`, `postgres_password`, `meilisearch_api_key`, `bexio_access_token`; `x-backend-volumes`: nur `${DATA_ROOT}/static:/static` und `${DATA_ROOT}/runtime:/run/forge:ro`.
- `django-migrate` command: `python manage.py check --deploy && python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py create_groups`.
- `web` command `["daphne", "-b", "0.0.0.0", "-p", "8000", "forge.asgi:application"]`, Healthcheck `http://127.0.0.1:8000/health/live/` mit `Host: ${APP_DOMAIN}`, `replicas: ${WEB_REPLICAS:-2}`.
- `celery-worker` command `celery -A forge worker --loglevel=INFO --queues=default,search.reconciliation --concurrency=${CELERY_CONCURRENCY:-2}`, `replicas: ${CELERY_REPLICAS:-1}`; `celery-beat` command `celery -A forge beat --loglevel=INFO --schedule=/data/celerybeat/celerybeat-schedule`, Volume nur `${DATA_ROOT}/celerybeat:/data/celerybeat`.
- `nginx`: Build ohne `args`/`secrets`; Environment `APP_DOMAIN`, `MONITORING_DOMAIN`, `ADMIN_DOMAIN`, `TLS_*`, `ADMIN_HTPASSWD_FILE`; Volumes TLS, `${DATA_ROOT}/static:/static:ro`, `${DATA_ROOT}/runtime:/run/forge:ro`.
- `celery-exporter` image `ghcr.io/danihodovic/celery-exporter:0.12.2`.
- `backup`: Volumes `${DATA_ROOT}/backups:/backups/local`, `${BACKUP_SHARE}:/backups/share` (keine files/templates); `restore-verify`: `MEDIA_ROOT` entfällt, Volumes `${RESTORE_BACKUP}:/restore/source:ro`, `${DATA_ROOT}/restore-verification/files:/restore/files`, `restore_postgres_data:/restore/postgres:ro`.
- `pgadmin` Login-Banner `'Authorized Forge administrators only'`.
- `NO_PROXY`-/`HTTP_PROXY`-Variablen bleiben (leer im `.env.example`).

`.env.example`: Quelle: Referenzprojekt, ohne Wiki/MS/PRO.FILE/Legacy/Automation/O-Z/Exports/Daily-Report-Blöcke; Werte: `COMPOSE_PROJECT_NAME=forge`, `DATA_ROOT=/srv/forge/data`, `DEPLOY_GROUP=forge-deploy`, `BACKUP_SHARE=/srv/forge/backup-share`, `RESTORE_BACKUP=/srv/forge/backup-share/REPLACE_WITH_BACKUP`, `TLS_CERT_FILE=/etc/forge/tls/fullchain.pem`, `TLS_KEY_FILE=/etc/forge/tls/privkey.pem`, `APP_DOMAIN=forge.example.local`, `MONITORING_DOMAIN=monitoring.forge.example.local`, `ADMIN_DOMAIN=db.forge.example.local`, `APP_HOST_ALIASES=localhost,127.0.0.1`, `CSRF_TRUSTED_ORIGINS=https://forge.example.local`, `HTTP_PORT=80`, `HTTPS_PORT=443`, `POSTGRES_DB=forge`, `POSTGRES_USER=forge`, `POSTGRES_CONN_MAX_AGE=0`, `PGBOUNCER_MAX_CLIENT_CONN=200`, `PGBOUNCER_DEFAULT_POOL_SIZE=20`, `PGBOUNCER_RESERVE_POOL_SIZE=5`, `WEB_REPLICAS=2`, `CELERY_REPLICAS=1`, `CELERY_CONCURRENCY=2`, `DEPLOY_MAINTENANCE_TIMEOUT_SECONDS=3600`, `RESTORE_MAINTENANCE_TIMEOUT_SECONDS=7200`, `MIN_FREE_GB=5`, Observability-Block (`PUSHGATEWAY_URL`, `PGADMIN_DEFAULT_EMAIL=admin@forge.example.local`, Retentions, `OBSERVABILITY_RUNBOOK_BASE_URL=https://github.com/EliasBauer/Forge/blob/main/deploy/runbooks`), Alerting-Block (`ALERT_TEAMS_ENABLED=false`, SMTP-Defaults wie Quelle), Proxy-Block, `NO_PROXY=localhost,127.0.0.1,nginx,web,postgres,pgbouncer,redis,meilisearch,grafana,loki,prometheus,pgadmin,alloy,node-exporter,pgbouncer-exporter,blackbox-exporter,pushgateway`. Kein `DEPLOY_GROUP_GID` (wird zur Laufzeit aufgelöst).

Dockerfiles/Entrypoints/nginx wie Spec-Abschnitte "Images" und "nginx". `deploy/nginx/nginx.conf.template`: Quelle das Referenzprojekt; Änderungen: Port-80-Block nur `location / { return 404; }` (kein MS-Callback), Upstream `forge_web`, Wartungs-Ausnahmen `/nginx-healthz`, `/maintenance.html`, `/logo.svg`; Locations `/static/`, `^/(graphql|api|admin|health)(/|$)`, `= /index.html`, `/`; Maintenance-Flag `/run/forge/maintenance`; Monitoring-/Admin-Blöcke identisch mit `Forge administration`. `maintenance.html`: Quelle, Texte deutsch ("Wir sind bald zurück"), Logo `/logo.svg`, kein PNG, keine Mailadresse.

Contract-Tests: Ports der Tests des Referenzprojekts ohne Wiki/Legacy/Automation/MS: Service-Menge (`CORE_RENDERED_SERVICES = {postgres, pgbouncer, redis, meilisearch, django-migrate, web, celery-worker, celery-beat, nginx}`), Profile per `docker compose config --services` (Skip ohne Docker; Env `DEPLOY_GROUP_GID=1000`), nur nginx publiziert Ports, `group_add` == Secret-Konsumenten, `search-index` one-shot, `web.deploy.replicas == "${WEB_REPLICAS:-2}"`, Singletons 1 Replikat, read-only Runtime, Worker-Queues, Observability profile-gated + gepinnte Images (Docker Hub oder `ghcr.io/danihodovic/celery-exporter`), Alloy-Host-Zugriff, Alertmanager-Egress, node-exporter Textfile, blackbox-Netze, Retention, Prometheus-DNS-SD `forge-web`, pgadmin intern; nginx: Virtual-Hosts, Redirects, WebSocket-Header, Maintenance-Guard, kein `resolve`, SPA-Revalidierung, http2; image: Basis-Images, non-root, `uv sync --frozen --no-dev`, `postgresql-client`, EXPOSE, `.dockerignore`, Secrets-Beispiele = `CHANGE_ME` (außer `bexio_access_token`, `teams_workflow_url`, `smtp_password` leer).

- [x] Tests → Dateien → `devcontainer exec … pytest deploy/tests -q --no-cov` grün → auf dem Host zusätzlich `docker compose --env-file deploy/.env.example -f deploy/compose.yml config --quiet` (mit `DEPLOY_GROUP_GID=1000 RESTORE_BACKUP=/tmp`) für alle Profile → Gate → Commit `feat(deploy): Compose-Stack, Images, nginx, Secrets-Vorlagen und Contract-Tests`

---

### Task 6: Betriebsskripte + Skript-Tests

**Files:** `deploy/scripts/{compose.sh,deploy.sh,validate-config.sh,maintenance.sh,restore-postgres.sh,render-observability-config.sh,validate-observability-config.sh,send-test-alert.sh,validate-teams-workflow.sh,start-all.sh,start-ops.sh}`, `deploy/scripts/lib/{compose.sh,operation-lock.sh}`, `deploy/backup/{backup.sh,restore-verify.sh}`, `deploy/tests/test_scripts.py`

Quelle: jeweils gleichnamige Datei des Referenzprojekts. Änderungen:
- `lib/operation-lock.sh`: erlaubte Operationen `deploy | restore | reset`; Fehlermeldung entsprechend.
- `maintenance.sh`: Metrikdateien `forge_maintenance.prom`, `forge_deployment.prom`, Metriknamen `forge_maintenance_*`, `forge_deployment_timestamp_seconds`, mktemp-Präfixe `.forge_*`.
- `deploy.sh`: `--scale "web=${WEB_REPLICAS:-2}" --scale "celery-worker=${CELERY_REPLICAS:-1}"`; `reset_application_cache` ruft `compose exec -T web python manage.py shell -c 'from django.core.cache import cache; cache.clear()'`; Kommentarblock ohne `celery-priority`.
- `validate-config.sh`: ohne Wiki-Lib, MS, Legacy-Cache, Teams-Sonderfall bleibt, ohne `TEMP_EXPORT_HOST_ROOT`/`O_DRIVE_ROOT`/`Z_DRIVE_ROOT`/`templates`/`files`/`automation`; Zertifikat-Schlüssel-Vergleich über `openssl x509 -pubkey -noout` vs. `openssl pkey -pubout`; zusätzliche Identitätsprüfungen: `prometheus`, `pushgateway` (65534:65534), `grafana` (472:0), `loki` (10001:10001), `pgadmin` (5050:5050), `restore-verification/files` (1000); `bexio_access_token.txt` leer → `printf 'preflight warning: …' >&2`, nicht fatal; Default `MIN_FREE_GB=5`.
- `backup/backup.sh`: ohne `files.tar`/`templates.tar`; `SHA256SUMS` über `database.dump manifest.txt`; Pushgateway-Job `forge_backup`.
- `backup/restore-verify.sh`: ohne tar-Entpacken; `python manage.py check` und `showmigrations --plan` ohne `--settings`; Job `forge_restore_verification`.
- `restore-postgres.sh`: unverändert bis auf Namen.
- `start-all.sh`/`start-ops.sh`: Service-Listen ohne `legacy-response-redis(-exporter)`, `celery-priority`, `celery-automation`.
- `send-test-alert.sh`: Alertname `ForgeNotificationTest`, Texte "Forge".
- Alle Skripte `chmod 0755`.

Tests (`deploy/tests/test_scripts.py`, Port ausgewählter Fälle des Referenzprojekts mit denselben Fake-Bin-Harnessen): Preflight (Gruppe fehlt/keine Mitgliedschaft/flock fehlt/GID nicht numerisch/Shared-Mode/Env-Secret-Modi/Platzhalter-Secret/Zertifikat-Mismatch/Bexio-leer-Warnung), Operation-Lock (blockiert zweiten Prozess, wiederverwendbar, Metadaten ohne Token), Maintenance (start/finish Metriken, ungültige Eingaben, status, reset-all mit Confirm, falscher Token), deploy.sh (Reihenfolge backup<migrate<reindex<up, Fehler vor/nach Maintenance, Signale), Backup-/Restore-Finalizer-Metriken, restore-postgres (Confirm + Pfad), render-observability (atomar, Teams aus, SMTP-Auth aus, Rollback), compose-Lib (v2/Standalone/Fehler), Start-Helfer (`sh -n`, exakte Service-Listen, Stop bei Fehler), alle Skripte ausführbar + `sh -n`.

- [x] Tests → Skripte → grün → Gate → Commit `feat(deploy): Betriebsskripte (deploy, maintenance, lock, backup, restore, ops) mit Tests`

---

### Task 7: Observability-Konfiguration + Runbook + Tests

**Files:** `deploy/prometheus/{prometheus.yml,alerts.yml.tmpl,recording-rules.yml,blackbox-targets.yml.tmpl,recording-rules.test.yml,grafana-annotations.test.yml,grafana-curated.test.yml}`, `deploy/prometheus/tests/alerts.test.yml`, `deploy/alertmanager/alertmanager.yml.tmpl`, `deploy/blackbox/blackbox.yml`, `deploy/loki/loki.yml`, `deploy/alloy/config.alloy`, `deploy/runbooks/alerts.md`, `deploy/tests/test_observability_config.py`

Änderungen gegenüber Quelle: `prometheus.yml` ohne Job `legacy-response-redis`, Job `forge-web`; `recording-rules.yml` = die fünf Spec-Regeln (Gruppe `forge-api-recording`, ohne Legacy-/Traffic-Share-Regeln); `alerts.yml.tmpl` ohne `LegacyRest5xx*`, `LegacyResponseRedis*`, Container-OOM-Regex `web|celery-worker|postgres|redis|meilisearch`, `TelemetryTargetDown` unverändert; `alertmanager.yml.tmpl` Subject `[Forge][…]`, Test-Alert `ForgeNotificationTest`, Inhibition `equal` ohne Änderung, `time_intervals` nur `Europe/Zurich` 07:00–18:00, Intervall-Name `business-hours`; `loki.yml` Prefix `forge_index_`; `alloy` unverändert; Fixtures ohne Legacy-Fälle, `api_latency_cross_api` nutzt `api="auth"`; Runbook ohne Legacy-Abschnitte, Einleitung ohne Legacy-Cache-Absatz.

Tests: Port mit `ALERT_MATRIX` (37 Einträge), Label-Policy, Ausdrucks-Semantik (ohne REST-Prüfungen), Annotationen ↔ Runbook, Alertmanager-Routen/Inhibition/Business-Hours (ein Intervall), Blackbox-Module/-Targets, Prometheus-Jobs/-Mounts/-Retention, Alloy-Level-Extraktion, Recording-Rule-Fixture, promtool-Fixture-Abdeckung (`ALERT_FIXTURE_CASES`).

Zusätzlich auf dem Host (Docker) ausführen und im README dokumentieren:
```bash
docker run --rm -v "$PWD/deploy/prometheus:/rules:ro" --entrypoint /bin/promtool prom/prometheus:v3.12.0 test rules /rules/tests/alerts.test.yml /rules/recording-rules.test.yml /rules/grafana-annotations.test.yml /rules/grafana-curated.test.yml
```

- [x] Tests → Dateien → grün → promtool grün → Gate → Commit `feat(deploy): Prometheus-Regeln, Alertmanager, Blackbox, Loki, Alloy, Runbook`

---

### Task 8: Grafana-Provisioning und Dashboard-Generator

**Files:** `deploy/grafana/provisioning/datasources/datasources.yml`, `deploy/grafana/provisioning/dashboards/dashboards.yml`, `deploy/grafana/provisioning/{alerting,plugins}/.gitkeep`, `deploy/grafana/scripts/{__init__.py,dashboardlib.py,dashboard_specs.py,build_dashboards.py}`, `deploy/grafana/dashboards/**/forge-*.json` (generiert), `deploy/tests/test_grafana_contract.py`

Änderungen: `dashboardlib.py` byte-identisch bis auf `tags=("forge", "production")` und vollständige Typannotationen (`dict[str, Any]`), damit `mypy --strict` besteht; `build_dashboards.py` `UID_COMPONENT = re.compile(r"forge-[A-Za-z0-9][A-Za-z0-9_-]*")`, `_owned` prüft `forge-`; `dashboard_specs.py` alle UIDs/Links `forge-*`, Titel "Forge …", Legacy-REST-Panels entfallen (Overview: "Legacy REST 5xx ratio / requests", "GraphQL vs REST traffic share", "Top remaining legacy REST endpoint groups"; API: alle "Legacy REST …"-Panels und "GraphQL vs REST migration trend"), Recording-Rule-Namen `forge:*`, Metriken `forge_*`, Queue-Variable auf `forge_celery_queue_depth`, Dependency-Scan-Jobs ohne legacy, Async-Dashboard ohne Legacy-Redis. Provisioning-Provider `name: Forge`.

Generieren: `devcontainer exec --workspace-folder . uv run python deploy/grafana/scripts/build_dashboards.py` und `… --check` → Exit 0.

Tests: Port der dashboardlib-Einheitentests (Query-Target-Form, Grid, Thresholds, Ref-IDs, Verbote), Render-Sicherheit (Duplikate, unsichere Pfade), `test_generated_dashboards_are_current`, Provisioning, exakte Dashboard-Menge je Ordner, Links auf Overview/Detail, Variablen referenziert, keine `or vector(0)`, Logs-Panels ohne Data-Links, Continuity nutzt `backup_*`-Namen, Overview-Annotationen mit `forge_deployment_timestamp_seconds`/`forge_maintenance_*`.

- [x] Tests → Dateien → generieren → grün → Gate → Commit `feat(deploy): Grafana-Provisioning und deterministischer Dashboard-Generator`

---

### Task 9: Deploy-Runbook

**Files:** `deploy/README.md`

Quelle: README des Referenzprojekts; Struktur übernehmen (Host-Voraussetzungen, Deploy-Gruppe, Verzeichnisse mit Eigentümern, Dev-Zertifikate, DNS, Erst-Deployment, Test-Server-Checkliste, Routine, Retry/Recovery, Passwort-Mismatch, start-ops/start-all, Alert-Verifikation, Skalierung, Backups, Restore-Verification, PostgreSQL-Restore, Zertifikat-Rotation, Incident-Recovery, promtool-Tests, Dashboards regenerieren), auf Deutsch, Forge-Pfade, ohne Wiki/MS/PRO.FILE/Automation/Legacy/Corporate-CA/GitHub-Token. Verzeichnis-Block:

```bash
sudo groupadd --force forge-deploy && sudo usermod -aG forge-deploy "$USER"
sudo mkdir -p /srv/forge/data/{postgres,redis,meilisearch,static,run,runtime/node-exporter,backups,celerybeat,alertmanager,prometheus,grafana,loki,alloy,pushgateway,pgadmin,restore-verification/files} /srv/forge/backup-share /etc/forge/tls
sudo chown -R 1000:1000 /srv/forge/data/{static,backups,celerybeat,restore-verification} /srv/forge/backup-share
sudo chmod 0755 /srv/forge/data/static
sudo chmod 0750 /srv/forge/data/{backups,celerybeat,restore-verification} /srv/forge/backup-share
sudo chown 65534:65534 /srv/forge/data/{alertmanager,prometheus,pushgateway} && sudo chmod 0750 /srv/forge/data/{alertmanager,prometheus,pushgateway}
sudo chown 472:0 /srv/forge/data/grafana && sudo chmod 0750 /srv/forge/data/grafana
sudo chown 10001:10001 /srv/forge/data/loki && sudo chmod 0750 /srv/forge/data/loki
sudo chown 5050:5050 /srv/forge/data/pgadmin && sudo chmod 0750 /srv/forge/data/pgadmin
sudo chgrp forge-deploy /srv/forge/data/{run,runtime} && sudo chmod 2770 /srv/forge/data/{run,runtime}
sudo chgrp forge-deploy /srv/forge/data/runtime/node-exporter && sudo chmod 2775 /srv/forge/data/runtime/node-exporter
```

- [x] Schreiben → Runbook-Tests aus Task 6/7 (Abschnitte vorhanden, Code-Fences balanciert) grün → Gate → Commit `docs(deploy): Runbook`

---

### Task 10: Gesamtgate, Review, Push

- [x] `devcontainer exec --workspace-folder . uv run pre-commit run --all-files` grün; `npm --prefix frontend run build` im Container erfolgreich (Vite-Build, wie im nginx-Image).
- [x] Host: `docker compose … config --quiet` für Default und jedes Profil; promtool-Tests; `docker build -f deploy/backend/Dockerfile .` und `docker build -f deploy/nginx/Dockerfile .` auf dem Mac (arm64) als Vorab-Test der Images.
- [x] `git push -u origin implement_deploy`.

---

### Task 11: Rollout auf `<operator>@<testserver>`

- [ ] Host vorbereiten (Task-9-Block per ssh mit sudo), `/etc/hosts` auf dem Pi: `127.0.0.1 <testserver> monitoring.<testserver> db.<testserver>`; Zertifikat:

```bash
sudo openssl req -x509 -nodes -newkey rsa:4096 -sha256 -days 3650 -keyout /etc/forge/tls/privkey.pem -out /etc/forge/tls/fullchain.pem -subj "/CN=<testserver>" -addext "subjectAltName=DNS:<testserver>,DNS:monitoring.<testserver>,DNS:db.<testserver>,IP:<LAN-IP>"
sudo chmod 0600 /etc/forge/tls/privkey.pem; sudo chmod 0644 /etc/forge/tls/fullchain.pem
```
  Hinweis: nginx läuft als root im Container und liest den Key; die Datei bleibt 0600 root.
- [x] `git clone -b implement_deploy https://github.com/EliasBauer/Forge.git ~/forge`; `deploy/.env` aus Beispiel (Domains `<testserver>`, `monitoring.<testserver>`, `db.<testserver>`; `CSRF_TRUSTED_ORIGINS=https://<testserver>`; `APP_HOST_ALIASES=localhost,127.0.0.1,<LAN-IP>`); Secrets per `openssl rand -base64 48 | tr -d '\n' > secrets/<name>.txt`, `admin_htpasswd.txt` = `printf 'admin:%s\n' "$(openssl passwd -apr1 "$PW")"`, `bexio_access_token.txt`, `teams_workflow_url.txt` leer (`install -m 0640 /dev/null`), `smtp_password.txt` leer; `chgrp forge-deploy .env secrets/*.txt; chmod 0640 …`. Erzeugte Admin-/Grafana-/pgAdmin-Passwörter dem Benutzer ausschließlich als Dateipfade nennen, nie im Chat ausgeben.
- [ ] Neue SSH-Sitzung (Gruppe), `./scripts/validate-config.sh`, `./scripts/deploy.sh`, `./scripts/start-ops.sh`, `./scripts/compose.sh ps`.
- [ ] Smoke vom Mac mit `curl --resolve`: `/health/live/`, `/health/ready/`, GraphQL-Probe, WebSocket-Handshake (`connection_init` → `connection_ack` per `python3 - websockets`-Skript oder `curl --include --http1.1 -H "Upgrade: websocket"` auf 101), `/api/login/` mit Superuser (`compose.sh exec web python manage.py createsuperuser --noinput` mit `DJANGO_SUPERUSER_*`), Grafana `/api/health`, pgAdmin Basic-Auth 401→200, Maintenance-Status, Backup-Profil, Restore-Verification, `maintenance.sh status`, Speicherverbrauch (`free -h`, `docker stats --no-stream`).
- [ ] Erkenntnisse (falsche Eigentümer, fehlende Pakete, Timing) ins README/Preflight zurückspielen, committen, pushen, auf dem Pi `git pull` + erneut deployen, bis der dokumentierte Pfad ohne Handarbeit durchläuft.


## Rollout-Protokoll (2026-09-13, `<operator>@<testserver>`)

Ablauf: Host-Prep (Skript `~/forge-host-prep.sh`, per sudo durch den Benutzer) → Clone → `.env`/Secrets auf dem Pi → `validate-config.sh` → `deploy.sh` → `start-ops.sh` → Smoke-Tests → Backup → Restore-Verification.

Funde, alle in den Branch zurückgespielt:
- `.env.example` war durch `deploy/.env.*` gitignored → `!deploy/.env.example` (047039f).
- Blackbox-Probe kann `.local`-Namen nicht auflösen → `extra_hosts: APP_DOMAIN:host-gateway` (30410d0); selbstsigniertes Zertifikat → `TLS_CERT_FILE` als CA-Datei im Blackbox-Container (fe107de).
- nginx: `zone forge_web 64k` ist auf 16-KB-Seiten-Hosts (Pi 5) zu klein → 256k (d1aad2a).
- `SOURCE_REVISION` aus `.env` überschrieb die Git-Revision → nur noch aus Git, auch für manuelle Backups über `compose.sh` (d1aad2a, fe107de).
- TLS-Key muss für die Deploy-Gruppe lesbar sein (Preflight läuft als Operator) → Runbook (1ce59f9); auf dem Pi liegt das Testzertifikat deshalb unter `~/forge-tls`.
- pgAdmin lehnt `.local`-Login-Adressen ab → Preflight-Check + Default `admin@forge-betrieb.de` (fe107de).
- Raspberry Pi OS ohne Memory-Cgroup-Accounting: Container-Speichermetriken leer → Runbook „Bekannte Grenzen".

Verifiziert (vom Mac per `curl --resolve`, WebSocket per Python-Client, Rest auf dem Pi): Health live/ready/maintenance 200, SPA + Logo + Admin-Static, `/admin/login/` 200, HTTP→HTTPS 308, unbekannter Host 404, Basic-Auth 401/200, `/api/login/` mit falschen Daten 401 und mit dem angelegten Admin 200, GraphQL-HealthProbe `{"data":{"__typename":"Query"}}`, WebSocket `connection_ack` + offene Subscription, Grafana health + 2 Datasources + 20 Dashboards in 3 Ordnern, Loki mit Logs aller 22 Services, 17 Prometheus-Targets `up`, pgAdmin hinter Basic-Auth 200, 3 Backups lokal + im Share mit gültigen Checksummen. Wartungsmodus nach Deploy beendet (`forge_maintenance_mode 0`, `forge_deployment_timestamp_seconds{revision="d1aad2a"}`).

Zugangsdaten (nur auf dem Pi): `~/forge-admin-credentials.txt`.
