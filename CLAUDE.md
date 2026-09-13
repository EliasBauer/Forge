# CLAUDE.md — Forge

> Prozess (Brainstorming, Planung, TDD, Code-Review, Branch-Flow) liegt bei **Superpowers** und triggert automatisch.
> Diese Datei trägt nur, was Superpowers nicht wissen kann: Forge-Umgebung, Test-Befehle, GM- und Frontend-Regeln.

## Umgebung — zwei Modi. ERST prüfen, dann handeln
Die Session kann **im DevContainer** oder **auf dem Host** gestartet worden sein. Beides ist gültig; du entscheidest nicht, du stellst fest. Allererster Befehl der Session:

```bash
test -f /.dockerenv && echo MODUS-CONTAINER || echo MODUS-HOST
```

Das Ergebnis legt für die ganze Session das **Präfix** fest, das in dieser Datei `<EXEC>` heißt:

| | Modus CONTAINER | Modus HOST |
|---|---|---|
| Wie gestartet | Claude Code läuft **in** dem DevContainer | Claude Code läuft daneben, der Container ist ein eigener Prozess |
| `<EXEC>` | *leer* — Befehle direkt ausführen | `devcontainer exec --workspace-folder .` |
| Container starten | entfällt, er läuft ja schon | einmal zu Beginn: `devcontainer up --workspace-folder .` |
| Worktrees | **keine** anlegen/wechseln — der Container ist der Worktree; Isolation = Branch | ein Worktree pro Container ist das normale Vorgehen |
| `docker` verfügbar | nein → Docker-Aufgaben an den Nutzer | ja |

Also: `<EXEC> uv run --group dev pytest tests/…`, `<EXEC> npm --prefix frontend test`, `<EXEC> git commit -m "…"` — in Modus CONTAINER ohne Präfix, in Modus HOST mit. Niemals `docker exec` und niemals ein fester Container-Name; in Modus HOST ordnet `--workspace-folder .` den passenden Container selbst zu. Fehlt dort die CLI: `npm install -g @devcontainers/cli`.

**Nur Modus HOST, einmal nach dem ersten `up` verifizieren:** `devcontainer exec --workspace-folder . git status`. Ein Worktree-`.git` verweist auf einen Host-Pfad; kommt „not a git repository", fehlt dem Container die Git-Datenbank → Mount nötig (Ein-Zeilen-Fix in der `devcontainer.json`). Dann stoppen und melden, nicht basteln.

## Schneller Test-Loop
Gezielt: `<EXEC> uv run --group dev pytest tests/pfad/test_x.py` (Backend) · `<EXEC> npm --prefix frontend test` (Frontend).
„Erledigt" erst, wenn das volle Gate **grün** ist: `<EXEC> pre-commit run --all-files` (ruff, pytest, mypy, vitest).

## Commit
`<EXEC> git commit` — so laufen die pre-commit-Hooks im Container, wo sie hingehören. **Niemals `--no-verify`** — das überspringt genau die Prüfung, die grün sein soll.
Commit die Specs-Datei die von superpowers generiert wird.
Bei jedem Task-Commit die zugehörige Plan-Datei mit in `git add` aufnehmen — sonst werden die abgehakten Boxen nie mitcommittet.

## Compose-Smoke-Test (ganzer Stack, immer auf dem HOST)
Zweck: prüfen, ob die *zusammengebaute* App startet — nicht Code ändern. Der Compose-Stack ist eine ANDERE Umgebung als der DevContainer, deshalb roh auf dem Host, **nie** mit `<EXEC>` davor. In Modus CONTAINER gibt es `docker` hier gar nicht → die Befehle dem Nutzer geben, statt sie selbst zu versuchen.
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