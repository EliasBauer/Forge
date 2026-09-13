# Deploy-Setup nach dem Muster eines ähnlichen Projekts (Docker Compose, Single-Host)

**Datum:** 2026-09-13
**Status:** Entwurf, genehmigt zur Umsetzung (Scope-Vorgabe: kompletter Aufbau des Referenzprojekts, 2 `web`-Instanzen)

## Kontext

Forge läuft bisher nur im Devcontainer. Die im Repo liegenden Deploy-Reste
(`docker/`, `nginx/`, `frontend/Dockerfile`, `frontend/nginx.conf`,
Root-`.env.example`, README-Verweis auf `test_docker/`) sind veraltet und
unbenutzbar. In einem ähnlichen Projekt existiert mit dessen `deploy/`-Ordner ein
erprobtes Single-Host-Compose-Setup (GeneralManager-Backend, gleiche
Toolchain). Forge soll denselben Aufbau bekommen, inklusive Observability,
Administration, Backup/Restore-Verification und Maintenance-System, aber mit
nur zwei Daphne-Instanzen.

Ziel-Host für den Test: Raspberry Pi 5 (`<operator>@<testserver>`, Debian 13
arm64, Docker 26 + Compose 2.26 + buildx, Ports 80/443 frei, passwortloses
sudo). Der Kundenserver ist später ein x86-64-Linux-Host; alle Images müssen
daher multi-arch sein.

## Ziel

- Ordner `deploy/` mit derselben Struktur, denselben Skripten, Profilen und
  Betriebskonzepten wie `<Referenzprojekt>/deploy`, angepasst auf Forge.
- Forge-Backend deploy-fähig: Secrets aus Dateien, Health-Endpoints,
  Prometheus-Metriken, JSON-Logs, WebSocket-Route für Subscriptions,
  Sicherheits-Settings hinter nginx.
- Verifizierter Rollout auf `<testserver>` über den dokumentierten
  Runbook-Pfad (`/srv/forge`, `/etc/forge/tls`, Deploy-Gruppe), Smoke-Tests
  über HTTPS, Backup- und Restore-Lauf.
- Branch `implement_deploy`, Spec und Plan committet, Push nach GitHub (der Pi
  clont von dort). `.env` und `secrets/*.txt` entstehen nur auf dem Pi und sind
  gitignored.

## Nicht-Ziele (fachlich nicht auf Forge übertragbar)

- Wiki.js-Migration, Legacy-API-Response-Cache-Redis, PRO.FILE-Bridge,
  Microsoft-SSO, O-/Z-Laufwerke, Export-Verzeichnis, Templates-Volume.
- Die Queues `celery-priority` und `celery-automation`: Forge hat nur die
  Default-Queue plus GMs `search.reconciliation`.
- Media-/File-Uploads (Forge hat keinen `MEDIA_ROOT`); das Backup sichert nur
  PostgreSQL.
- CI-Workflows (Forge hat keine GitHub Actions); die Contract-Tests laufen im
  Devcontainer über `pytest`.
- Kein Umbau der Forge-Fachlogik. Frontend bleibt unverändert.

## Namensschema

| Referenzprojekt | Forge |
| --- | --- |
| Compose-Projekt `referenz`, Images `referenz-backend/-nginx` | `forge`, `forge-backend`, `forge-nginx` |
| Metriken `referenz_*`, Recording-Rules `referenz:*` | `forge_*`, `forge:*` |
| Alerts `Referenz*` | `Forge*` |
| Grafana-UIDs `referenz-*` | `forge-*` |
| Prometheus-Job `referenz-web` | `forge-web` |
| Pushgateway-Jobs `referenz_backup`, `_restore_verification`, `_celery_queues` | `forge_backup`, `forge_restore_verification`, `forge_celery_queues` |
| Loki-Index-Prefix `referenz_index_` | `forge_index_` |
| Flag-Datei `/run/referenz/maintenance` | `/run/forge/maintenance` |
| Textfile-Metriken `referenz_maintenance.prom`, `referenz_deployment.prom` | `forge_maintenance.prom`, `forge_deployment.prom` |
| Pfade `/srv/referenz`, `/etc/referenz/tls` | `/srv/forge/data`, `/srv/forge/backup-share`, `/etc/forge/tls` |
| Gruppe `referenz-deploy` | `forge-deploy` |
| Runbook-Basis-URL | `https://github.com/EliasBauer/Forge/blob/main/deploy/runbooks` |
| Test-Alert `ReferenzNotificationTest`, Subject `[Referenz]` | `ForgeNotificationTest`, `[Forge]` |
| Business-Hours-Fenster (14 Zeitzonen) | Mo–Fr 07:00–18:00 `Europe/Zurich` |

## Architektur

### Compose-Services

| Profil | Service | Image | Replikate / Rolle |
| --- | --- | --- | --- |
| Kern | postgres | postgres:17-alpine | 1, Bind-Mount `${DATA_ROOT}/postgres`, Netz `data` |
| Kern | pgbouncer | edoburu/pgbouncer:v1.24.1-p1 | 1, Transaction-Pooling, Entrypoint aus `pgbouncer/entrypoint.sh` |
| Kern | redis | redis:7-alpine | 1, AOF, Cache + Channel-Layer + Celery-Broker (eine DB, wie in Forge-Settings) |
| Kern | meilisearch | getmeili/meilisearch:v1.45.0 | 1, Master-Key aus Secret, Metriken aktiviert |
| Kern | django-migrate | forge-backend | one-shot: `check --deploy`, `migrate`, `collectstatic`, `create_groups`; `POSTGRES_HOST=postgres` |
| deployment | search-index | forge-backend | one-shot `search_index --reindex` |
| Kern | **web** | forge-backend (daphne) | **2** (`WEB_REPLICAS`), read-only Root-FS, tmpfs `/tmp`, über pgbouncer |
| Kern | celery-worker | forge-backend | `CELERY_REPLICAS` (Default 1), Queues `default,search.reconciliation` |
| Kern | celery-beat | forge-backend | 1, Schedule-Datei in `${DATA_ROOT}/celerybeat` |
| Kern | nginx | forge-nginx | 1, einziger Host-Port (`HTTP_PORT`/`HTTPS_PORT`), Frontend-Build im Image |
| observability | prometheus, alertmanager, blackbox-exporter, grafana, loki, alloy, node-exporter, postgres-exporter, pgbouncer-exporter, redis-exporter, celery-exporter, nginx-exporter, pushgateway | wie das Referenzprojekt gepinnt; celery-exporter von `ghcr.io/danihodovic/celery-exporter:0.12.2` (Docker-Hub-Tag ist nur amd64) | wie das Referenzprojekt |
| administration | pgadmin | dpage/pgadmin4:9.15.0 | hinter `ADMIN_DOMAIN` mit htpasswd |
| backup | backup | forge-backend | one-shot `backup/backup.sh` |
| restore-verification | restore-postgres, restore-verify | postgres:17-alpine, forge-backend | isoliertes Netz, temporäres Volume |

Netze: `ingress`, `application`, `data`, `observability`, `alerting-egress`,
`restore-verification` (internal). Compose-Anker `x-security-defaults`,
`x-secret-security-defaults` (`group_add: ${DEPLOY_GROUP_GID}`),
`x-backend-environment`, `x-backend-secrets`, `x-backend-build` wie im Vorbild.

Secrets (Dateien in `deploy/secrets/`, je mit `.example`): `django_secret_key`,
`postgres_password`, `meilisearch_api_key`, `bexio_access_token` (darf leer
sein: dann Bexio-Dev-Modus mit Fixtures, Preflight warnt), `admin_htpasswd`,
`grafana_admin_password`, `pgadmin_password`, `teams_workflow_url` (leer
erlaubt bei `ALERT_TEAMS_ENABLED=false`, Default), `smtp_password`
(`/dev/null` bei `ALERT_SMTP_AUTH_ENABLED=false`, Default).

Backend-Umgebung (Auszug): `FORGE_ENV=production`, `DJANGO_SECRET_KEY_FILE`,
`ALLOWED_HOSTS=${APP_DOMAIN},web,${APP_HOST_ALIASES}`,
`INTERNAL_METRICS_HOST=web`, `CSRF_TRUSTED_ORIGINS` (Default
`https://${APP_DOMAIN}`), `POSTGRES_*` + `POSTGRES_PASSWORD_FILE`,
`POSTGRES_CONN_MAX_AGE=0`, `REDIS_URL=redis://redis:6379/0`,
`MEILISEARCH_URL`, `MEILISEARCH_MASTER_KEY_FILE`, `BEXIO_ACCESS_TOKEN_FILE`,
`STATIC_ROOT=/static`, `MAINTENANCE_FLAG_FILE=/run/forge/maintenance`,
`LOG_TO_STDOUT=true`, `PUSHGATEWAY_URL`.

### Images

- `deploy/backend/Dockerfile`: `python:3.12-slim-trixie` (PostgreSQL-Client 17
  passt zu `postgres:17`), `uv` per pip in der Devcontainer-Version
  (0.12.13), `uv sync --frozen --no-dev` in `/app/.venv`, `PYTHONPATH=/app/src`,
  non-root `appuser` 1000:1000, apt: `ca-certificates curl postgresql-client
  rsync`. Kopiert nur `pyproject.toml`, `uv.lock`, `manage.py`, `src/`,
  `deploy/backend/entrypoint.sh`, `deploy/backup/*.sh`. Kein BuildKit-Cache-
  Mount, keine Build-Secrets (Frontend hat keine privaten Pakete).
- `deploy/nginx/Dockerfile`: Stage `node:22-slim` (`npm ci`, `vite build`),
  Stage `debian:trixie-slim` mit `nginx curl openssl gettext-base`; Frontend-
  `dist` nach `/usr/share/nginx/html`, Template + Entrypoint + Wartungsseite.
- Root-`.dockerignore` schließt `.git`, `**/.env`, `deploy/.env*`,
  `deploy/secrets/*.txt`, `node_modules`, `dist`, `.venv`, Caches aus.
  Secrets dürfen nie in ein Image gelangen.

### nginx

Drei TLS-Virtual-Hosts (`APP_DOMAIN`, `MONITORING_DOMAIN` → Grafana,
`ADMIN_DOMAIN` → pgAdmin mit Basic-Auth). HTTP:80 antwortet für Monitoring-/
Admin-Domain mit `308` auf HTTPS, sonst `404`. App-Host: SPA (`try_files`),
`/static/` Alias, `/graphql`, `/api`, `/admin`, `/health` an `web` (HTTP/1.1,
Upgrade-Header für WebSockets, 300 s Read-Timeout); `/metrics` wird bewusst
nicht proxied (Prometheus scrapt `web:8000` direkt). Maintenance-Flag
`/run/forge/maintenance` liefert `503` mit `maintenance.html` (Forge-Logo aus
dem Frontend-Build), ausgenommen `/nginx-healthz` und die Seiten-Assets.
`stub_status` auf Port 8080 für den nginx-Exporter. Kein HSTS-Header (die
Kunden-Zertifikate sind voraussichtlich selbstsigniert; HSTS würde den
Browser-Click-through blockieren).

### Skripte (`deploy/scripts`)

Übernommen und umbenannt: `compose.sh`, `lib/compose.sh` (Gruppen-Auflösung,
Compose-v2/Standalone-Fallback), `lib/operation-lock.sh` (Operationen
`deploy|restore|reset`), `maintenance.sh` (start/finish/finish-command/
publish-deploy/reset-all/status mit Lease, Token, Textfile-Metriken),
`deploy.sh` (Lock → validate → build → Postgres bereit → Credential-Check →
Maintenance → Backup → migrate → search-index → `up -d --scale web=2 --scale
celery-worker=N` → Health inkl. GraphQL-Probe → publish-deploy → finish →
Cache leeren), `restore-postgres.sh`, `render-observability-config.sh`,
`validate-observability-config.sh`, `send-test-alert.sh`,
`validate-teams-workflow.sh`, `start-ops.sh`, `start-all.sh`.

`validate-config.sh` prüft: Tools (docker, flock, getent, stat, openssl),
`DEPLOY_GROUP` + Mitgliedschaft, `docker info`, Domains (drei, verschieden),
`compose config`, TLS-Paar (Public-Key-Vergleich, damit RSA und EC
funktionieren) und Ablauf, `DATA_ROOT`/`BACKUP_SHARE` + freier Platz
(`MIN_FREE_GB`, Default 5), Shared-Verzeichnisse `run`/`runtime` (2770) und
`runtime/node-exporter` (2775), app-eigene Verzeichnisse (`static`, `backups`,
`celerybeat`, `restore-verification/files`, `BACKUP_SHARE` → UID 1000),
Identitäts-Verzeichnisse `alertmanager`/`prometheus`/`pushgateway` (65534),
`grafana` (472), `loki` (10001), `pgadmin` (5050), Secrets (gruppenprivat,
nicht `CHANGE_ME`; `bexio_access_token` leer = Warnung), keine Host-Ports auf
`postgres|redis|meilisearch|pgbouncer`.

Cache leeren nach Deploy: `python manage.py shell -c "from django.core.cache
import cache; cache.clear()"` (Forge hat kein `clear_cache`-Command).

### Observability

- Prometheus: Jobs `prometheus`, `alertmanager`, `forge-web` (DNS-SD über
  `web`, Port 8000, `/metrics`), `postgres`, `redis`, `celery`, `nginx`,
  `node`, `pgbouncer`, `alloy`, `loki`, `blackbox` (File-SD), `meilisearch`
  (Bearer aus Secret), `pushgateway`. Retention 45 d / 10 GB.
- Recording-Rules: `forge:api_requests:rate5m`,
  `forge:graphql_server_faults:rate5m`,
  `forge:api_request_duration_seconds:p95_5m`,
  `forge:graphql_request_duration_seconds:p95_5m`,
  `forge:graphql_errors:ratio5m`.
- Alerts (37): alle Alerts des Referenzprojekts außer `LegacyRest5xx*` und
  `LegacyResponseRedis*`, umbenannt auf `Forge*`, gleiche Ausdrücke, Labels
  (`severity`, `service`, `notification_scope`, `alert_family`,
  `maintenance_sensitive`, `root_cause`/`dependency`) und Annotationen
  (`summary`, `impact`, `first_action`, `dashboard_url`, `runbook_url`).
- Alertmanager: gleiche Routen/Inhibitionen, Teams optional (`# TEAMS_ONLY`),
  SMTP-Auth optional (`# SMTP_AUTH_ONLY`), ein Business-Hours-Intervall.
- Blackbox: `https_2xx` auf `/health/live/`, `graphql_health` auf die
  `HealthProbe`-Query, `internal_http_2xx` auf Meilisearch.
- Loki 7 d Retention, Alloy: Docker-Logs (Level aus JSON `levelname` oder
  Celery-Plaintext) + cAdvisor-Metriken per Remote-Write.
- Grafana: Provisioning (Prometheus + Loki), Dashboards deterministisch aus
  `grafana/scripts/dashboard_specs.py` generiert (`build_dashboards.py`,
  `--check` im Test). 20 Dashboards: `forge-overview` (Operations); Curated
  `forge-api`, `forge-async-redis`, `forge-continuity`, `forge-logs-changes`,
  `forge-postgres-pgbouncer`, `forge-search`, `forge-host-containers`;
  Exporters `forge-node-exporter`, `forge-cadvisor`, `forge-postgres-exporter`,
  `forge-pgbouncer-exporter`, `forge-redis-exporter`, `forge-celery-exporter`,
  `forge-nginx-exporter`, `forge-meilisearch-detail`, `forge-prometheus-detail`,
  `forge-alertmanager-detail`, `forge-loki-detail`, `forge-alloy-detail`.
  Legacy-REST-Panels entfallen; das API-Label kennt `graphql` und `auth`
  (`/api/login/`, `/api/logout/`).
- Runbook `runbooks/alerts.md`: ein Abschnitt je Alert (Impact, drei Checks,
  Recovery, Eskalation).
- promtool-Unit-Tests: `prometheus/tests/alerts.test.yml`,
  `recording-rules.test.yml`, `grafana-annotations.test.yml`,
  `grafana-curated.test.yml`, ohne Legacy-Fälle. Ausführung über `docker run
  prom/prometheus … promtool test rules` (dokumentiert im README; nicht Teil
  des Devcontainer-Gates, da dort kein Docker läuft).

### Backend-Änderungen (Forge)

- `src/forge/env.py`: `env_bool`, `env_csv`, `env_int`, `env_secret`
  (`NAME_FILE` vor `NAME`, `required` → `ImproperlyConfigured`).
- `src/forge/settings.py`:
  - `IS_DEV = FORGE_ENV == "dev"`; Prod verlangt `DJANGO_SECRET_KEY`.
  - `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` (Default `http://localhost:5173`),
    `INTERNAL_METRICS_HOST`, `STATIC_ROOT`, `MAINTENANCE_FLAG_FILE`,
    `PUSHGATEWAY_URL` aus der Umgebung.
  - Prod-DB: `django_prometheus.db.backends.postgresql`, `POSTGRES_*`,
    Passwort per `env_secret`, `CONN_MAX_AGE` (Default 0),
    `CONN_HEALTH_CHECKS`, `DISABLE_SERVER_SIDE_CURSORS` (pgbouncer
    Transaction-Pooling), `connect_timeout`. `dj-database-url` entfällt.
  - `INSTALLED_APPS` + `django_prometheus`; Middleware:
    `InternalMetricsHostMiddleware`, `PrometheusBeforeMiddleware`,
    `ApiMetricsMiddleware`, bestehende Kette, `PrometheusAfterMiddleware`.
  - Meilisearch-Key und Bexio-Token per `env_secret`.
  - Celery: `WORKER_SEND_TASK_EVENTS`, `TASK_SEND_SENT_EVENT`,
    `TASK_TRACK_STARTED`, `TASK_ACKS_LATE`, `WORKER_PREFETCH_MULTIPLIER=1`,
    Zeitlimits 1800/1680 s, `TASK_DEFAULT_QUEUE="default"`; Beat-Eintrag
    `publish-observability-queue-metrics` (60 s) nur in Prod.
  - `GENERAL_MANAGER`: `GRAPHQL_METRICS_ENABLED` (Prod), Backend
    `prometheus`, Allowlist aus `forge/graphql_metric_operations.py`,
    Unknown-Policy `unknown`, kein Resolver-Timing.
  - Prod-Security: `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST`,
    `SECURE_SSL_REDIRECT` (Default an, Exempt `health/`, `metrics`),
    Secure-Cookies, `SECURE_CONTENT_TYPE_NOSNIFF`, HSTS über
    `DJANGO_SECURE_HSTS_SECONDS` (Default 0, dokumentiert).
  - Prod-Logging: JSON auf stdout (`python-json-logger`), Level `LOG_LEVEL`.
- `src/forge/observability/`: `api_metrics.py`
  (`forge_api_requests_total{api,endpoint_group,method,status}`,
  `forge_api_request_duration_seconds`), `graphql_probe.py`, `middleware.py`,
  `metrics_host.py`, `celery_queue_metrics.py` (Queues `default`,
  `search.reconciliation`, Header `forge_published_at`, Job
  `forge_celery_queues`), `tasks.py` (`publish_observability_queue_metrics`).
- `src/forge/health.py` + `urls.py`: `/health/live/`, `/health/ready/`,
  `/health/maintenance/`, `django_prometheus.urls` (`/metrics`).
- `src/forge/asgi.py`: WebSocket-Route `^graphql/?$` auf GMs
  `GraphQLSubscriptionConsumer` hinter `AuthMiddlewareStack`.
- `src/forge/celery.py`: zusätzlich `autodiscover_tasks(["forge.observability"])`.
- `pyproject.toml`: + `django-prometheus`, `prometheus-client`,
  `python-json-logger`, `redis`; − `dj-database-url`; dev + `pyyaml`;
  `testpaths` + `deploy/tests`; mypy-Hook prüft zusätzlich `deploy`.
- Tests (100 % Coverage bleibt Pflicht): `env.py`, Health-Views, WebSocket-
  Route, API-Metriken/Probe/Middleware/Metrics-Host, Queue-Metriken,
  Allowlist gegen den Frontend-Quelltext, Celery-Konfiguration.
- Aufräumen: `docker/`, `nginx/`, `frontend/Dockerfile`, `frontend/nginx.conf`,
  Root-`.env.example` löschen; README-Abschnitte "Setup Schritt 4" und
  "Deployment" ersetzen; `docs/architektur.md` (Verzeichnisstruktur,
  Settings-Tabelle, Deployment-Tabelle) und `docs/start_dev.md` anpassen;
  ADR 006 "Deployment als Single-Host Docker Compose nach dem Muster eines ähnlichen Projekts".

### Contract-Tests (`deploy/tests`)

Fokussierte Ports der Tests des Referenzprojekts: `test_compose_contract.py`
(Service-Menge, Profile per `docker compose config` wenn Docker verfügbar,
nur nginx publiziert Ports, Secret-Gruppen, Replikate, Read-only-Runtime,
Exporter-Verdrahtung, Restore-Isolation), `test_nginx_contract.py`,
`test_image_contract.py`, `test_observability_config.py` (Alert-Matrix,
Label-Policy, Annotationen ↔ Runbook, Alertmanager-Routen, Blackbox,
Prometheus-Jobs, Alloy-Level-Extraktion, promtool-Fixture-Abdeckung),
`test_grafana_contract.py` (dashboardlib-Einheiten, generierte Dashboards
aktuell, Provisioning, Links/Variablen, kein `or vector(0)`),
`test_scripts.py` (Preflight mit Fake-Bin-Oberfläche, Operation-Lock,
Maintenance start/finish/status/reset-all, deploy.sh-Reihenfolge und
Fehlerpfade, Backup-Finalizer-Metriken, render-observability atomar,
compose-Lib-Fallback, Start-Helfer, POSIX-Syntax aller Skripte).

## Testserver-Rollout (`<operator>@<testserver>`)

1. Host: Gruppe `forge-deploy` + Mitgliedschaft, `/srv/forge/data/*`,
   `/srv/forge/backup-share`, `/etc/forge/tls` mit den im README
   dokumentierten Eigentümern/Modi; selbstsigniertes Zertifikat mit SAN
   `<testserver>`, `monitoring.<testserver>`, `db.<testserver>`,
   IP `<LAN-IP>`; `/etc/hosts` auf dem Pi für die drei Namen.
2. `git clone -b implement_deploy https://github.com/EliasBauer/Forge.git ~/forge`.
3. `deploy/.env` aus `.env.example`, Secrets per `openssl rand -base64 48`
   (htpasswd per `openssl passwd -apr1`), Modus 0640, Gruppe `forge-deploy`.
4. `./scripts/validate-config.sh`, `./scripts/deploy.sh`, `./scripts/start-ops.sh`.
5. Smoke: `https://<testserver>/health/live|ready/`, GraphQL-Probe,
   WebSocket `connection_ack`, Login im Frontend (Admin-User per
   `createsuperuser`), `https://monitoring.<testserver>/api/health`,
   pgAdmin-Login, `./scripts/compose.sh --profile backup run --rm backup`,
   Restore-Verification, `./scripts/maintenance.sh status`.
   Browser-Zugriff vom Mac braucht `/etc/hosts`-Einträge für die drei Namen.

## Risiken und Entscheidungen

- Ressourcen: ~25 Container auf 8 GB RAM. Erwartet ~4 GB; wenn der Pi
  swappt, werden `WEB_REPLICAS` und Prometheus-Retention im `.env` reduziert,
  nicht die Struktur.
- Bind-Mount-Eigentümer der Observability-Dienste (Prometheus/Grafana/Loki/
  pgAdmin laufen als eigene UIDs) werden im Preflight geprüft; das Referenzprojekt
  dokumentiert das nicht explizit, Forge tut es.
- `.local`-Subdomains lösen per mDNS nicht auf; Tests nutzen `curl --resolve`,
  Browser-Zugriff über `/etc/hosts`.
