# Architektur – Forge

> Stand: 2026-06-16

## Überblick

Forge ist eine Intranet-Webanwendung für kleine Handwerksbetriebe (~10 Personen). Sie löst Papier und Excel im Projektcontrolling ab und verbindet sich mit dem ERP Bexio.

```
Browser (React/TS)
    │  GraphQL (HTTP + WS)
    ▼
Django (ASGI / Daphne)
    ├── GeneralManager (Domain Layer)
    ├── graphene-django (GraphQL Schema)
    └── Celery Worker + Beat (Async Tasks)
         │
         ├── PostgreSQL 16
         ├── Redis (Cache + Channel Layer + Celery Broker)
         └── Meilisearch (Volltextsuche, Prod)
```

## Tech-Stack

| Schicht                  | Technologie                            |
| ------------------------ | -------------------------------------- |
| Backend                  | Python ≥ 3.12, Django ≥ 5.2            |
| Domain Framework         | GeneralManager (PyPI)                  |
| API                      | GraphQL via graphene + graphene-django |
| Realtime                 | Django Channels + channels-redis       |
| Datenbank                | PostgreSQL 16                          |
| Cache / Broker           | Redis                                  |
| Suche (Dev)              | DevSearchBackend (kein Service nötig)  |
| Suche (Prod)             | MeilisearchBackend                     |
| Async Tasks              | Celery (Worker + Beat)                 |
| Frontend                 | React + TypeScript (Vite)              |
| GraphQL Client           | Apollo Client                          |
| Package Manager Backend  | uv                                     |
| Package Manager Frontend | npm                                    |

## Verzeichnisstruktur

```
forge/
├── src/
│   ├── forge/                       # Django-Projekt (settings, urls, asgi, wsgi)
│   │   ├── env.py                   # Umgebungs-Helfer (Docker-Secrets NAME_FILE)
│   │   ├── health.py                # /health/live|ready|maintenance
│   │   └── observability/           # API-/Queue-Metriken, Metrics-Host, Probe
│   └── apps/
│       ├── authentication/          # Login, Gruppen, Berechtigungen
│       │   ├── managers.py          # Benutzer/Gruppe GM-Manager (Wrapper um User/Group)
│       │   ├── models.py            # History-Model-Anker (simple_history für User/Group)
│       │   ├── graphql_capabilities.py # globaler me.capabilities-Provider
│       │   ├── management/commands/ # create_groups.py, setup_dev_data.py
│       │   ├── migrations/
│       │   └── tests/
│       ├── bexio/                   # Bexio-Spiegel (Konten, Lieferantenrechnungen)
│       │   ├── models/              # konto.py, lieferantenrechnung.py
│       │   ├── calculation_manager/ # IstWert, ProjektKennzahlen
│       │   │   ├── ist_wert.py      # Bexio-Kosten je Kostenart
│       │   │   └── projekt_kennzahlen.py
│       │   ├── tests/
│       │   ├── admin.py
│       │   ├── migrations/
│       │   ├── services.py          # API-Client
│       │   ├── sync.py              # Sync-Logik (Celery-Tasks)
│       │   └── tasks.py
│       ├── projekt/                 # Kern-Domain: Projekt, Kostenart, KostenPosition
│       │   ├── models/              # projekt.py, kostenart.py, kosten_position.py
│       │   ├── manager/
│       │   ├── tests/
│       │   ├── admin.py
│       │   ├── migrations/
│       │   └── signals.py
│       └── stunden/                 # Stundensatz pro Jahr
│           ├── models/              # stundensatz.py
│           ├── calculation_manager/ # AufgabenStundensatz (fehlende Jahre)
│           │   └── aufgaben_stundensatz.py
│           ├── tests/
│           ├── admin.py
│           └── migrations/
├── frontend/
│   └── public/                      # Logo, Farbpalette
│   └── src/
│       ├── App.tsx
│       ├── components/              # Layout.tsx, ProtectedRoute.tsx
│       ├── contexts/                # AuthContext.tsx
│       ├── graphql/                 # queries.ts, mutations.ts, subscriptions.ts
│       ├── lib/apolloClient.ts
│       ├── pages/                   # AufgabenPage, LoginPage, ProjektListePage,
│       │                            # ProjektDetailPage, ProjektNeuPage, StundensaetzePage
│       └── utils/                   # format.ts, deviation.ts
├── deploy/             # Docker-Compose-Deployment (Runbook: deploy/README.md)
│   ├── compose.yml     # Kern + Profile observability/administration/backup/restore-verification
│   ├── backend/, nginx/ # Dockerfiles, Entrypoints, nginx-Template
│   ├── scripts/        # deploy.sh, validate-config.sh, maintenance.sh, backup/restore
│   ├── prometheus/, alertmanager/, grafana/, loki/, alloy/, blackbox/
│   ├── secrets/        # *.txt.example (echte Dateien sind gitignored)
│   └── tests/          # Contract-Tests (pytest)
├── tests/              # Integrations- und System-Tests (cross-cutting)
├── docs/                             # Dokumentation
│   ├── specs/                        # Feature-Specs je Domain (+ designs/ für Claude.ai-Handoffs)
│   └── superpowers/                  # Superpowers-Artefakte: plans/ und specs/ pro Task
├── pyproject.toml
└── .pre-commit-config.yaml
```

## Settings & Umgebungsvariablen

`FORGE_ENV=dev` (Devcontainer) schaltet SQLite, `DEBUG`, unsicheren Secret-Key
und Bexio-Fixtures ein. Ohne `FORGE_ENV` gilt Produktion: PostgreSQL, Pflicht-
Secret, Security-Settings hinter nginx, JSON-Logs, GraphQL-Metriken.
Jedes Secret wird bevorzugt aus `NAME_FILE` (Docker-Secret) gelesen
(`forge/env.py`).

| Variable                        | Default (Prod)                     | Bedeutung                                  |
| ------------------------------- | ---------------------------------- | ------------------------------------------ |
| `DJANGO_SECRET_KEY[_FILE]`      | Pflicht                            | Django Secret                              |
| `ALLOWED_HOSTS`                 | `localhost,127.0.0.1`              | Erlaubte Hosts                             |
| `CSRF_TRUSTED_ORIGINS`          | `http://localhost:5173`            | Origins für CSRF (Admin)                   |
| `POSTGRES_HOST/PORT/DB/USER`    | `pgbouncer/5432/forge/forge`       | PostgreSQL-Verbindung                      |
| `POSTGRES_PASSWORD[_FILE]`      | Pflicht                            | PostgreSQL-Passwort                        |
| `POSTGRES_CONN_MAX_AGE`         | `0`                                | 0 = pro Request (pgBouncer)                |
| `REDIS_URL`                     | leer → LocMem/InMemory             | Cache, Channel-Layer, Celery-Broker        |
| `MEILISEARCH_URL`               | leer → DevSearchBackend            | Suche                                      |
| `MEILISEARCH_MASTER_KEY[_FILE]` | leer                               | Meilisearch-Key                            |
| `BEXIO_ACCESS_TOKEN[_FILE]`     | leer → Fixture-Modus               | Bexio-API                                  |
| `INTERNAL_METRICS_HOST`         | leer                               | Host-Alias für Prometheus-Scrapes          |
| `STATIC_ROOT`                   | `src/staticfiles`                  | collectstatic-Ziel                         |
| `MAINTENANCE_FLAG_FILE`         | `/run/forge/maintenance`           | Wartungsflag (nginx 503)                   |
| `PUSHGATEWAY_URL`               | leer                               | Celery-Queue-Metriken                      |
| `LOG_TO_STDOUT`                 | `true` (Prod)                      | JSON-Logs auf stdout                       |
| `DJANGO_SECURE_HSTS_SECONDS`    | `0`                                | HSTS nur mit vertrauenswürdigem Zertifikat |

## Frontend-Routing

| Pfad              | Seite                   | Zugriff                      |
| ----------------- | ----------------------- | ---------------------------- |
| `/login`          | Login                   | öffentlich                   |
| `/`               | — Redirect →            | `/projekte`                  |
| `/aufgaben`       | Aufgaben / Onboarding   | alle authentifizierten User  |
| `/projekte`       | Projektliste            | alle authentifizierten User  |
| `/projekte/neu`   | Neues Projekt anlegen   | Admin, Projektleiter         |
| `/projekte/:id`   | Projektdetail           | alle authentifizierten User  |
| `/stundensaetze`  | Stundensätze verwalten  | Admin, Projektleiter         |

## Corporate Design

Design-Tokens (Logo: `frontend/public/logo.svg`):

| Token         | Hex       |
| ------------- | --------- |
| Black         | `#000000` |
| Dark Gray     | `#2B2A29` |
| Blue (Akzent) | `#6D82F7` |
| Red (Akzent)  | `#E42127` |

## Deployment (Single-Host Docker Compose)

Aufbau nach dem Muster eines ähnlichen Projekts (ADR 006), Runbook: `deploy/README.md`.

| Profil               | Container                                                                                                      | Rolle                                   |
| -------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| Kern                 | `nginx`                                                                                                        | TLS, SPA, Reverse Proxy, einziger Host-Port |
| Kern                 | `web` ×2                                                                                                       | Django / Daphne (ASGI)                  |
| Kern                 | `celery-worker`, `celery-beat`                                                                                 | Async-Tasks, Bexio-Sync, Search-Reconcile |
| Kern                 | `postgres`, `pgbouncer`, `redis`, `meilisearch`                                                                | Daten, Pooling, Cache/Broker, Suche     |
| Kern / `deployment`  | `django-migrate`, `search-index`                                                                               | One-shot: Migrationen, Static, Reindex  |
| `observability`      | `prometheus`, `alertmanager`, `blackbox-exporter`, `grafana`, `loki`, `alloy`, `node-exporter`, `*-exporter`, `pushgateway` | Metriken, Logs, Alerts, Dashboards |
| `administration`     | `pgadmin`                                                                                                      | DB-Administration hinter Basic-Auth     |
| `backup`             | `backup`                                                                                                       | pg_dump + Checksummen + Transfer        |
| `restore-verification` | `restore-postgres`, `restore-verify`                                                                         | isolierte Restore-Probe                 |
