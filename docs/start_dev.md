# Dev-Setup – Forge

## Voraussetzungen

- Python ≥ 3.12 (empfohlen: via `pyenv`)
- Node.js ≥ 20 + npm
- [uv](https://docs.astral.sh/uv/) installiert
- PostgreSQL 16 laufend (lokal oder via Docker)
- Redis laufend (lokal oder via Docker)

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

Die App läuft ohne `.env`-Datei mit folgenden Defaults:

| Variable       | Default                                    |
| -------------- | ------------------------------------------ |
| `DATABASE_URL` | `postgres://forge:forge@localhost:5432/forge` |
| `REDIS_URL`    | `redis://localhost:6379/0`                 |
| `DEBUG`        | `true`                                     |

Für andere Werte eine `.env`-Datei anlegen (siehe `.env.example`).

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

## Schnellstart mit Docker (optional)

> Noch nicht implementiert – kommt in Phase 2.

## Pre-commit Checks

Bei jedem Commit laufen automatisch:

- `ruff check` + `ruff format --check` (Backend Lint/Format)
- `mypy` (Type Checking)
- `pytest` (Backend Tests)
- `vitest` (Frontend Tests)

Bei Fehlern wird der Commit abgebrochen. Fehler beheben, dann erneut committen.

## Memo für mich
`uv lock --upgrade-package generalmanager && uv sync 2>&1`
