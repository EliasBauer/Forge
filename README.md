# Forge

Forge ist eine interne Projektcontrolling-Webanwendung für Handwerksbetriebe mit Bexio-Integration. Sie ersetzt Papier und Excel im Projektcontrolling und holt Daten automatisch aus dem ERP Bexio.

## Features

- **Projektübersicht** — tagesaktuelle Kosten- und Kennzahlen pro Projekt (Offerte, WV, Ist)
- **Bexio-Sync** — automatischer täglicher Abgleich von Lieferantenrechnungen und Konten
- **Kostenarten** — strukturierte Gliederung in Ertrags- und Kostenblöcke
- **Stundensätze** — Verwaltung globaler Personalkosten-Sätze pro Kalenderjahr
- **Rollenbasierter Zugriff** — Admin, Projektleiter, Betrachter, Monteur
- **Live-Updates** — GraphQL Subscriptions über WebSocket
- **Suche** — Volltext-Suche über Projekte

## Screenshots

<img width="4082" height="563" alt="Bildschirmfoto 2026-06-16 um 05 34 42" src="https://github.com/user-attachments/assets/96963ac6-f809-4946-a778-eccaf464f81b" />  
<img width="1260" height="1514" alt="Bildschirmfoto 2026-06-16 um 05 34 58" src="https://github.com/user-attachments/assets/d52a4f7c-597c-4bae-938c-eab84e045db8" />  
<img width="709" height="324" alt="Bildschirmfoto 2026-06-16 um 05 35 09" src="https://github.com/user-attachments/assets/f2fb13d5-74b6-437f-9ead-0eb40b736335" />  



## Tech Stack

| Schicht    | Technologie                                      |
|------------|--------------------------------------------------|
| Backend    | Python 3.12, Django 6, GeneralManager 0.79       |
| API        | GraphQL (graphene-django), WebSockets (Channels) |
| Frontend   | React 18, TypeScript, Vite, Tailwind CSS         |
| Datenbank  | PostgreSQL 17 hinter pgBouncer                   |
| Cache/RT   | Redis                                            |
| Suche      | Meilisearch                                      |
| Deployment | Docker Compose, nginx, Daphne, Prometheus/Grafana/Loki |

## Lokale Entwicklung

### Voraussetzungen

- [uv](https://github.com/astral-sh/uv) (Python Package Manager)
- Node.js 20+
- Docker + Docker Compose (für PostgreSQL + Redis)

### Setup

```bash
# 1. Repo klonen
git clone https://github.com/EliasBauer/Forge.git
cd Forge

# 2. Python-Abhängigkeiten installieren
uv sync --group dev

# 3. Frontend-Abhängigkeiten installieren
cd frontend && npm install && cd ..

# 4. Dev-Modus aktivieren (im Devcontainer bereits gesetzt: SQLite, Fixture-Bexio)
export FORGE_ENV=dev

# 5. Datenbank migrieren
uv run python manage.py migrate

# 6. Dev-Daten anlegen (Gruppen, Testuser, Stundensätze, Demo-Projekte)
uv run python manage.py setup_dev_data

# 7. Backend starten
uv run python manage.py runserver

# 8. Frontend starten (separates Terminal)
cd frontend && npm run dev -- --host
```

Backend läuft auf `http://localhost:8000`, Frontend auf `http://localhost:5173`.

GraphQL Playground: `http://localhost:8000/graphql/`

### Tests

```bash
# Backend (pytest + Coverage)
uv run pre-commit run pytest --hook-stage manual

# oder direkt
cd src && uv run pytest ../tests/

# Frontend (vitest)
cd frontend && npm test
```

### Bexio-Integration

Ohne `BEXIO_ACCESS_TOKEN` läuft die App im Dev-Modus (Fixture-Daten statt echter API).
Mit Token werden Konten und Lieferantenrechnungen täglich automatisch synchronisiert.

Manueller Sync:
```bash
uv run python src/manage.py sync_bexio
```

## Deployment

Produktion läuft als Single-Host-Docker-Compose-Stack nach dem Muster eines ähnlichen Projekts: nginx (TLS, einziger Host-Port), zwei Daphne-Instanzen,
Celery Worker + Beat, PostgreSQL 17 hinter pgBouncer, Redis, Meilisearch,
dazu die Profile `observability` (Prometheus, Alertmanager, Grafana, Loki,
Alloy, Exporter), `administration` (pgAdmin), `backup` und
`restore-verification`. Konfiguration, Skripte und Runbook liegen unter
[`deploy/`](deploy/README.md). Einstieg: [`docs/start_prod.md`](docs/start_prod.md)
(Schritt für Schritt) und [`docs/explain_prod_setup.md`](docs/explain_prod_setup.md)
(was die Teile tun und warum).

Kurzfassung (Details und Host-Vorbereitung im Runbook):

```bash
cd deploy
cp .env.example .env && for f in secrets/*.txt.example; do cp "$f" "${f%.example}"; done
$EDITOR .env secrets/*.txt
./scripts/validate-config.sh
./scripts/deploy.sh
./scripts/start-ops.sh
```

## Lizenz

Copyright © 2026 Elias Bauer. Alle Rechte vorbehalten.  
Quellcode ist öffentlich einsehbar — kommerzielle Nutzung und Weiterverbreitung sind ohne ausdrückliche Genehmigung untersagt. Siehe [LICENSE](LICENSE).
