# CLAUDE.md — Forge

> Prozess (Brainstorming, Planung, TDD, Code-Review, Branch-Flow) liegt bei **Superpowers** und triggert automatisch.
> Diese Datei trägt nur, was Superpowers nicht wissen kann: Forge-Umgebung, Test-Befehle, GM- und Frontend-Regeln.

## Umgebung & wo Befehle laufen
Erkenne zu Beginn via `test -f /.dockerenv`:
- **existiert** → du bist IM DevContainer (CLI/VS Code). Dev-Befehle direkt ausführen.
- **fehlt** → du bist auf dem Host (Desktop App). Dev-Befehle wrappen:
  `docker exec -w /workspaces/Forge forge-dev <befehl>`

**Dev-Befehle** (Code/Tests/Linting) gehören in `forge-dev`: `uv`, `pytest`, `ruff`, `mypy`, `python manage.py`, `npm`, `pre-commit`.

**Orchestrierung roh auf dem Host, nie wrappen:** `docker`, `docker compose`, `gh` und die hook-freien Git-Kommandos (`add`, `status`, `log`, `diff`, `push`, `fetch`) laufen immer roh auf dem Host. `docker exec … docker compose …` ist immer falsch.

**Ausnahme `git commit`:** Der Commit triggert den pre-commit-Hook, der Dev-Tools (ruff/pytest/mypy/vitest) braucht — die gibt es nur im Container. Auf dem Host **im Container committen**:
`docker exec -w /workspaces/Forge forge-dev git commit -m "…"`
Niemals `--no-verify`, um den Hook zu umgehen — das verwirft genau die Prüfung, die grün sein soll.

## Schneller Test-Loop
Gezielt: `uv run --group dev pytest tests/pfad/test_x.py` (Backend) · `npm --prefix frontend test` (Frontend).
„Erledigt" erst, wenn das volle Gate **grün** ist: `pre-commit run --all-files` (ruff, pytest, mypy, vitest).

## Compose-Smoke-Test (ganzer Stack, auf dem HOST)
Zweck: prüfen, ob die *zusammengebaute* App startet und läuft — nicht Code ändern (dafür ist der DevContainer da).
Der Compose-Stack ist eine ANDERE Umgebung als `forge-dev`: „läuft im DevContainer" heißt nicht „läuft in Compose".
- Hoch:   `docker compose -f <DATEI> up -d --build`
- Status: `docker compose -f <DATEI> ps`  (alle Services healthy?) · Logs: `docker compose -f <DATEI> logs -f <SERVICE>`
- Check:  <SMOKE-CHECK, z.B. curl auf einen Health-Endpoint>
- Runter: `docker compose -f <DATEI> down`  (Volumes nur bewusst mit `-v`)
„Grün" heißt hier: Stack kommt hoch, Services healthy, Ziel-Endpoint antwortet — NICHT die Test-Suite.
Up/Down sind bewusste Aktionen, kein Teil des automatischen Task-Loops.

## Commit-Disziplin
Bei jedem Task-Commit die Plan-Datei mit in `git add` aufnehmen —
sonst werden die abgehakten Boxen des Tasks nie mitcommittet.

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