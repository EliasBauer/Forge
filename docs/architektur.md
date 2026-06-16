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
│   └── apps/
│       ├── authentication/          # Login, Gruppen, Berechtigungen
│       │   ├── management/commands/ # create_groups.py, setup_dev_data.py
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
│       └── utils/                   # format.ts, deviation.ts, permissions.ts
├── docker/             # Dockerfile + docker-compose.yml
├── nginx/              # nginx.conf (Reverse Proxy)
├── tests/              # Integrations- und System-Tests (cross-cutting)
├── docs/               # Dokumentation
├── specs/              # Feature-Specs und Todo
├── pyproject.toml
└── .pre-commit-config.yaml
```

## Settings & Umgebungsvariablen

| Variable            | Default (Dev)                              | Bedeutung                |
| ------------------- | ------------------------------------------ | ------------------------ |
| `DJANGO_SECRET_KEY` | insecure-dev-key                           | Django Secret            |
| `DEBUG`             | `true`                                     | Debug-Modus              |
| `ALLOWED_HOSTS`     | `localhost,127.0.0.1`                      | Erlaubte Hosts           |
| `DATABASE_URL`      | `postgres://forge:forge@localhost:5432/forge` | PostgreSQL DSN        |
| `REDIS_URL`         | `redis://localhost:6379/0`                 | Redis (Cache + Channels) |

Wenn `REDIS_URL` gesetzt: Redis-Cache + RedisChannelLayer.
Wenn nicht: LocMemCache + InMemoryChannelLayer (nur für lokale Tests ohne Redis).

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

## Deployment (Ziel: Raspberry Pi, Intranet)

Ziel-Setup via Docker Compose:

| Container       | Rolle                                 |
| --------------- | ------------------------------------- |
| `web`           | Django / Daphne (ASGI)                |
| `frontend`      | React Build (Vite / nginx)            |
| `nginx`         | Reverse Proxy + Static Files          |
| `db`            | PostgreSQL 16                         |
| `redis`         | Cache + Channel Layer + Celery Broker |
| `celery-worker` | Async Task Execution                  |
| `celery-beat`   | Scheduled Tasks (Bexio Sync)          |
| `meilisearch`   | Volltextsuche                         |

Docker Compose liegt in `docker/docker-compose.yml`.
