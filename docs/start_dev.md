# Dev-Setup – Forge

## Voraussetzungen

- Python ≥ 3.12 (empfohlen: via `pyenv`)
- Node.js ≥ 20 + npm
- [uv](https://docs.astral.sh/uv/) installiert
- Kein PostgreSQL/Redis nötig: `FORGE_ENV=dev` nutzt SQLite und In-Memory-Cache

## Ersteinrichtung

```bash
# 1. Python-Abhängigkeiten + Dev-Tools
uv sync --group dev

# 2. Frontend-Abhängigkeiten
npm --prefix frontend install

# 3. Pre-commit Hooks einrichten
uv run pre-commit install

# 4. Datenbank anlegen (PostgreSQL muss laufen)
uv run python manage.py migrate

# 5. Superuser anlegen
uv run python manage.py createsuperuser
```

## Entwicklungsserver starten

Zwei Terminals öffnen:

**Terminal 1 – Backend (Django/Daphne):**
```bash
uv run python manage.py runserver 0.0.0.0:8000
```

**Terminal 2 – Frontend (Vite):**
```bash
cd frontend && npm run dev -- --host
```

`--host` ist nötig, damit Vite auf `0.0.0.0` hört (wichtig im DevContainer).

Anschließend: [http://localhost:5173](http://localhost:5173)

## Umgebungsvariablen (Dev-Defaults)

Der Devcontainer setzt `FORGE_ENV=dev`; außerhalb davon `export FORGE_ENV=dev`.

| Variable            | Default (Dev)               | Bedeutung                                   |
| ------------------- | --------------------------- | ------------------------------------------- |
| `FORGE_ENV`         | `production` (!)            | `dev` = SQLite, DEBUG, Bexio-Fixtures       |
| `REDIS_URL`         | leer                        | gesetzt: Redis-Cache + RedisChannelLayer    |
| `MEILISEARCH_URL`   | leer                        | gesetzt: Meilisearch statt DevSearchBackend |
| `BEXIO_ACCESS_TOKEN`| leer                        | gesetzt: echte Bexio-API statt Fixtures     |

Vollständige Liste: `docs/architektur.md`, Abschnitt Settings.

## Tests

```bash
# Backend (pytest + coverage)
uv run pytest

# Frontend (vitest)
npm --prefix frontend test

# Oder einmalig alle Pre-commit Checks laufen lassen:
uv run pre-commit run --all-files
```

## Wichtige URLs (Dev)

| URL                              | Inhalt                      |
| -------------------------------- | --------------------------- |
| `http://localhost:5173`          | React Frontend              |
| `http://localhost:8000/graphql/` | GraphiQL (GraphQL Explorer) |
| `http://localhost:8000/admin/`   | Django Admin                |

## Deployment

Produktions-Stack (Docker Compose, nginx, Observability): Einstieg in
`start_prod.md`, Erklärung in `explain_prod_setup.md`, Betriebshandbuch in
`deploy/README.md`.

## Pre-commit Checks

Bei jedem Commit laufen automatisch:

- `ruff check` + `ruff format --check` (Backend Lint/Format)
- `mypy` (Type Checking)
- `pytest` (Backend Tests)
- `vitest` (Frontend Tests)

Bei Fehlern wird der Commit abgebrochen. Fehler beheben, dann erneut committen.

## Memo für mich
`uv lock --upgrade-package generalmanager && uv sync 2>&1`
