# CLAUDE.md — Forge

> Prozess (Brainstorming, Planung, TDD, Code-Review, Branch-Flow) liegt bei **Superpowers** und triggert automatisch.
> Diese Datei trägt nur, was Superpowers nicht wissen kann: Forge-Umgebung, Test-Befehle, GM- und Frontend-Regeln.

## Umgebung — eigener Container pro Worktree
Jeder Worktree läuft in seinem EIGENEN Container, gebaut aus `.devcontainer/devcontainer.json`. Der Agent läuft auf dem Host und spricht den Container über die `devcontainer`-CLI an — **nicht** über `docker exec`, **kein** fester Container-Name.

Zu Beginn der Session einmal (baut/startet den Container für DIESEN Worktree):
```bash
devcontainer up --workspace-folder .
```
Fehlt die CLI: `npm install -g @devcontainers/cli`.

Danach JEDEN Dev-Befehl über `devcontainer exec` in genau diesen Container:
```bash
devcontainer exec --workspace-folder . uv run --group dev pytest tests/…
devcontainer exec --workspace-folder . npm --prefix frontend test
devcontainer exec --workspace-folder . git commit -m "…"
```
`--workspace-folder .` = aktueller Worktree; die CLI ordnet den passenden Container selbst zu.

**Einmal verifizieren (Worktree-Eigenheit!):** direkt nach dem ersten `up`:
`devcontainer exec --workspace-folder . git status`
Ein Worktree-`.git` verweist auf einen Host-Pfad. Kommt „not a git repository", fehlt dem Container die Git-Datenbank → Mount nötig (Ein-Zeilen-Fix in der devcontainer.json). Dann stoppen und melden, nicht basteln.

## Schneller Test-Loop
Gezielt (im Container): `pytest tests/pfad/test_x.py` (Backend) · `npm --prefix frontend test` (Frontend).
„Erledigt" erst, wenn das volle Gate **grün** ist: `pre-commit run --all-files` (ruff, pytest, mypy, vitest).

## Commit
`git commit`; über `devcontainer exec` (dann laufen die pre-commit-Hooks im Container korrekt). **Niemals `--no-verify`** — das überspringt genau die Prüfung, die grün sein soll.
Commit die Specs-Datei die von superpowers generiert wird.
Bei jedem Task-Commit die zugehörige Plan-Datei mit in `git add` aufnehmen — sonst werden die abgehakten Boxen nie mitcommittet.

## Compose-Smoke-Test (ganzer Stack, auf dem HOST)
Zweck: prüfen, ob die *zusammengebaute* App startet — nicht Code ändern. Läuft roh auf dem Host, NICHT über devcontainer/exec.
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