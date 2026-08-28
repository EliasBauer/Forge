# CLAUDE.md — Forge

> Prozess (Brainstorming, Planung, TDD, Code-Review, Branch-Flow) liegt bei **Superpowers** und triggert automatisch.
> Diese Datei trägt nur, was Superpowers nicht wissen kann: Forge-Umgebung, Test-Befehle, GM- und Frontend-Regeln.

## Umgebung
Du läufst **immer im DevContainer** dieses Worktrees — eine in sich geschlossene Umgebung mit eigenem `uv`-venv und `node_modules`. Alle Dev-Befehle (`uv`, `pytest`, `ruff`, `mypy`, `python manage.py`, `npm`, `pre-commit`, `git commit`) führst du **direkt** aus, ohne `docker exec`-Wrapper.

Sicherheits-Check zu Beginn: `test -f /.dockerenv` muss existieren. Fehlt es, bist du versehentlich auf dem Host — dann **nicht** raten, sondern stoppen und den Nutzer bitten, den Worktree im Container zu öffnen.

## Schneller Test-Loop
Gezielt: `uv run --group dev pytest tests/pfad/test_x.py` (Backend) · `npm --prefix frontend test` (Frontend).
„Erledigt" erst, wenn das volle Gate **grün** ist: `pre-commit run --all-files` (ruff, pytest, mypy, vitest).

## Commit
Direkt `git commit` (im Container laufen die pre-commit-Hooks korrekt). **Niemals `--no-verify`** — das überspringt genau die Prüfung, die grün sein soll.
Bei jedem Task-Commit die zugehörige Plan-Datei (`docs/specs/plans/<task>.md`) mit in `git add` aufnehmen — sonst werden die abgehakten Boxen nie mitcommittet.

## Compose-Smoke-Test (ganzer Stack)
Zweck: prüfen, ob die *zusammengebaute* App startet — nicht Code ändern. Der Compose-Stack ist eine ANDERE Umgebung als der DevContainer.
- Hoch: `docker compose -f <DATEI> up -d --build` · Status: `… ps` · Logs: `… logs -f <SERVICE>`
- Check: <SMOKE-CHECK, z. B. curl auf einen Health-Endpoint> · Runter: `… down` (Volumes nur bewusst mit `-v`)
„Grün" heißt: Stack kommt hoch, Services healthy, Ziel-Endpoint antwortet — NICHT die Test-Suite. Up/Down sind bewusste Aktionen, kein Teil des Task-Loops.

## Code-Regeln

### GeneralManager (Details: `general-manager`-Skill)
- Feldzugriff IMMER via `self.feldname` — nie via `self._interface._instance`.
- Related-Lookups über den GM: `KostenPosition.filter(projekt=self.projekt)` statt raw ORM.

### Frontend
- Frontend macht KEINE Validierung, keine Permission-Checks, keine Zugriffslogik.
- Frontend-Aufgaben: Routing, Darstellung, User-Input, GraphQL-Queries/Mutations/Subscriptions, WebSockets, Server-Fehler anzeigen.

## Referenzen
- Projekt-Kontext: `CONTEXT.md` · Architektur-Entscheidungen: `docs/adr/`
- Bei Architektur-/Pattern-Änderungen `docs/` und `README.md` aktualisieren.