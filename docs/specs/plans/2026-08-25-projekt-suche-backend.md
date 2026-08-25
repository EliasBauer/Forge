# Projekt-Suche über das Backend (GM/Meilisearch) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Projektliste sucht über das GeneralManager-Suchbackend (Meilisearch produktiv, DevSearch lokal) statt über clientseitiges `Array.filter`.

**Architecture:** `SearchConfig` auf dem `Projekt`-Manager registriert `name`/`auftragsnummer`/`projektleiter__username` im GM-Suchindex „global". Das aktive Backend wird in `settings.py` per Env-Var-Vorhandensein gewählt (gleiches Muster wie `CACHES`/`CHANNEL_LAYERS`). Das Frontend ersetzt den Client-Filter durch eine debounced GraphQL-`search`-Query gegen denselben Endpunkt, nur bei nicht-leerem Suchfeld — leeres Feld zeigt weiterhin die unveränderte, live-subscribte Volltabelle.

**Tech Stack:** Django 5 / GeneralManager 0.76.0 / GraphQL (graphene-django) / React + Apollo Client 4 / Meilisearch (Python-Client `meilisearch`).

**Spec:** [docs/specs/projekt-suche-backend.md](../projekt-suche-backend.md)

## Global Constraints

- **Umgebung erkennen & wrappen (CLAUDE.md):** Backend-Befehle laufen im Devcontainer (`forge-dev`). Vom Host aus jeden Befehl wrappen:
  `docker exec -u vscode -w /workspaces/Forge forge-dev bash -lc "<befehl>"`
  (`bash -lc` lädt das Login-Profil, in dem `uv` unter `/home/vscode/.local/bin` im PATH liegt — ohne `-lc` schlägt `uv: not found` fehl.)
- **Worktree-Gotcha:** Arbeitest du in einem Git-Worktree unter `.claude/worktrees/<name>/`, zeigt dessen `.git`-Datei auf einen Host-absoluten Pfad, den der Container nicht kennt. Git-Befehle im Container brauchen deshalb:
  `-e GIT_DIR=/workspaces/Forge/.git/worktrees/<worktree-name> -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/<worktree-name>`
  zusätzlich zu `-w /workspaces/Forge/.claude/worktrees/<worktree-name>`.
- **„Erledigt" erst, wenn das volle Gate grün ist (CLAUDE.md):** `uv run pre-commit run --all-files` (ruff, pytest mit 100 % Coverage, mypy, vitest) — nicht nur der einzelne Test aus dem jeweiligen Task.
- **Commit-Disziplin (CLAUDE.md):** Committe nur, wenn ausdrücklich gesagt. Die Commit-Schritte unten sind vorbereitet (Nachricht, Dateien) — bei Ausführung durch einen Subagenten vor jedem `git commit` beim Menschen nachfragen, nicht automatisch committen.
- **GM-Feldzugriff** immer via `self.feldname`, nie `self._interface._instance` (GM-Skill, goldene Regel).
- **Related-Lookups über den GM**, nicht raw ORM (CLAUDE.md, GM-Skill).
- **Frontend macht keine Validierung/Permission-Checks** — Suchtreffer werden von GM serverseitig nach `Projekt.Permission.__read__` gefiltert (CLAUDE.md, Spec).

---

### Task 1: Such-Backend konfigurieren + Dependency

**Files:**
- Modify: `pyproject.toml` (Dependency, via `uv add`)
- Modify: `uv.lock` (automatisch durch `uv add`)
- Modify: `src/forge/settings.py:138-165`

**Interfaces:**
- Produces: `GENERAL_MANAGER["SEARCH_BACKEND"]`, `GENERAL_MANAGER["SEARCH_AUTO_REINDEX"]`, `GENERAL_MANAGER["SEARCH_RECONCILE_ENABLED"]`, `GENERAL_MANAGER["SEARCH_RECONCILE_INTERVAL_SECONDS"]` in Django-Settings — Task 2 verlässt sich darauf, dass `get_search_backend()` ohne weiteres Zutun ein nutzbares Backend liefert (DevSearch im Devcontainer, da `MEILISEARCH_URL` dort nicht gesetzt ist).

- [ ] **Step 1: Dependency hinzufügen**

```bash
docker exec -u vscode -w /workspaces/Forge forge-dev bash -lc "uv add meilisearch"
```

Erwartet: `pyproject.toml` bekommt einen neuen Eintrag `"meilisearch>=...",` in `dependencies`, `uv.lock` wird aktualisiert.

- [ ] **Step 2: Settings ändern**

In `src/forge/settings.py`, aktueller Block (Zeilen 138-165):

```python
# --- Celery ---
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Jeden Mittwoch um 02:00 Uhr (Europe/Zurich)
    "bexio-sync-weekly": {
        "task": "bexio.sync_lieferantenrechnungen",
        "schedule": crontab(hour=2, minute=0, day_of_week=3),
    },
}

GENERAL_MANAGER = {
    "AUTOCREATE_GRAPHQL": True,
    "GRAPHQL_URL": "graphql/",
    "DEFAULT_PERMISSIONS": {
        "READ": ["public"],
        "CREATE": ["isAuthenticated"],
        "UPDATE": ["isAuthenticated"],
        "DELETE": ["isAuthenticated"],
    },
}
```

Ersetzen durch:

```python
# --- Celery ---
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Jeden Mittwoch um 02:00 Uhr (Europe/Zurich)
    "bexio-sync-weekly": {
        "task": "bexio.sync_lieferantenrechnungen",
        "schedule": crontab(hour=2, minute=0, day_of_week=3),
    },
}

# --- Suche ---
# Kein MEILISEARCH_URL gesetzt (z. B. im Devcontainer) => GM faellt automatisch auf
# den in-memory DevSearchBackend zurueck (general_manager/search/backend_registry.py).
MEILISEARCH_URL = os.environ.get("MEILISEARCH_URL", "")

GENERAL_MANAGER = {
    "AUTOCREATE_GRAPHQL": True,
    "GRAPHQL_URL": "graphql/",
    "DEFAULT_PERMISSIONS": {
        "READ": ["public"],
        "CREATE": ["isAuthenticated"],
        "UPDATE": ["isAuthenticated"],
        "DELETE": ["isAuthenticated"],
    },
    "SEARCH_AUTO_REINDEX": True,
    "SEARCH_RECONCILE_ENABLED": True,
    "SEARCH_RECONCILE_INTERVAL_SECONDS": 30,
    "SEARCH_BACKEND": (
        {
            "class": "general_manager.search.backends.meilisearch.MeilisearchBackend",
            "options": {
                "url": MEILISEARCH_URL,
                "api_key": os.environ.get("MEILISEARCH_MASTER_KEY") or None,
            },
        }
        if MEILISEARCH_URL
        else None
    ),
}
```

- [ ] **Step 3: Verifizieren, dass Django sauber bootet**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/generalmanager-0-76-0-update-6899d6 forge-dev bash -lc "uv run python manage.py check"
```

Erwartet: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Volles Gate laufen lassen (Regressionscheck)**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/generalmanager-0-76-0-update-6899d6 forge-dev bash -lc "uv run pre-commit run --all-files"
```

Erwartet: alle fünf Hooks `Passed` (settings.py ist von Coverage ausgenommen, `tool.coverage.run.omit` in `pyproject.toml`, daher keine neuen Coverage-Anforderungen durch diesen Task).

- [ ] **Step 5: Commit** (nur nach expliziter Freigabe, s. Global Constraints)

```bash
git add pyproject.toml uv.lock src/forge/settings.py
git commit -m "feat: Such-Backend (Meilisearch/DevSearch) konfigurieren

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: SearchConfig auf `Projekt` + Backend-Test

**Files:**
- Modify: `src/apps/projekt/models/projekt.py:1-30` (Import), nach der `Permission`-Klasse (SearchConfig einfügen)
- Modify: `tests/test_graphql_queries.py` (neue Query-Konstante + Testmethode)

**Interfaces:**
- Consumes: `GENERAL_MANAGER["SEARCH_BACKEND"]` etc. aus Task 1 (indirekt, über `get_search_backend()`).
- Produces: GraphQL-Root-Query `search(query: String!, index: String, types: [String], pageSize: Int) { results { ... } total }`, nutzbar von Task 3 im Frontend. Fragment-Typname für `Projekt`-Treffer: `ProjektType` (verifiziert in `general_manager/api/graphql.py:791`, Suffix `Type` an jeden Manager-Klassennamen).

- [ ] **Step 1: Failing Test schreiben**

In `tests/test_graphql_queries.py`, nach `_QUERY_PROJEKT_DETAIL` (vor `class _SharedSetup`) einfügen:

```python
_QUERY_SEARCH_PROJEKTE = """
    query SearchProjekte($query: String!) {
      search(query: $query, index: "global", types: ["Projekt"], pageSize: 20) {
        results {
          ... on ProjektType {
            id
            name
            auftragsnummer
          }
        }
        total
      }
    }
"""
```

In `class GraphQLQueryShapeTest(_SharedSetup)`, nach `test_projekt_detail_shape` einfügen:

```python
    # ------------------------------------------------------------------
    # search (Projekt-Suche über das Backend)
    # ------------------------------------------------------------------

    def test_search_findet_projekt_nach_name(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            Projekt.create(
                ignore_permission=True,
                name="Lueftungsanlage Nord",
                auftragsnummer="T-2026-042",
                offerte_summe=Measurement(50_000, "CHF"),
                wv_summe=Measurement(45_000, "CHF"),
                jahr=2026,
            )
        result = _gql(
            self.client,
            _QUERY_SEARCH_PROJEKTE,
            variables={"query": "Lueftungsanlage"},
        )
        self.assertNotIn("errors", result, result.get("errors"))
        namen = [r["name"] for r in result["data"]["search"]["results"]]
        self.assertIn("Lueftungsanlage Nord", namen)
```

`self.captureOnCommitCallbacks(execute=True)` ist nötig, weil GM die Indexierung über
`transaction.on_commit(...)` registriert (`general_manager/search/invalidation.py`) — Djangos
`TestCase` führt `on_commit`-Callbacks sonst nicht aus, der Treffer bliebe unsichtbar. Da
`SEARCH_ASYNC` nicht gesetzt ist (Task 1, bewusst ausgelassen laut Spec), läuft die Indexierung
inline (kein Celery-Worker im Test nötig).

- [ ] **Step 2: Test laufen lassen, erwartet FAIL**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/generalmanager-0-76-0-update-6899d6 forge-dev bash -lc "uv run pytest tests/test_graphql_queries.py::GraphQLQueryShapeTest::test_search_findet_projekt_nach_name -v"
```

Erwartet: FAIL — `search` ist als Root-Query-Feld vorhanden (GM registriert es global), aber die
Suche liefert keine Treffer, weil `Projekt` noch keine `SearchConfig` hat (`results` ist leer,
`namen` enthält `"Lueftungsanlage Nord"` nicht → `AssertionError`).

- [ ] **Step 3: `SearchConfig` implementieren**

In `src/apps/projekt/models/projekt.py`, Import-Block erweitern (nach der bestehenden
`general_manager`-Import-Zeile):

```python
from general_manager import (
    AdditiveManagerPermission,
    DatabaseInterface,
    FieldConfig,
    GeneralManager,
    IndexConfig,
)
```

Nach der `Permission`-Klasse (vor `@classmethod def create`) einfügen:

```python
    class SearchConfig:
        indexes = [
            IndexConfig(
                name="global",
                fields=[
                    "name",
                    "auftragsnummer",
                    FieldConfig(name="projektleiter__username", boost=1.5),
                ],
            )
        ]
```

- [ ] **Step 4: Test laufen lassen, erwartet PASS**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/generalmanager-0-76-0-update-6899d6 forge-dev bash -lc "uv run pytest tests/test_graphql_queries.py::GraphQLQueryShapeTest::test_search_findet_projekt_nach_name -v"
```

Erwartet: PASS

- [ ] **Step 5: Volles Gate laufen lassen**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/generalmanager-0-76-0-update-6899d6 forge-dev bash -lc "uv run pre-commit run --all-files"
```

Erwartet: alle Hooks `Passed`, inkl. 100 % Coverage (die `SearchConfig`-Klasse selbst ist
deklarativer Code, wird beim Modul-Import bereits ausgeführt — kein separater Coverage-Bedarf).

- [ ] **Step 6: Commit** (nur nach expliziter Freigabe)

```bash
git add src/apps/projekt/models/projekt.py tests/test_graphql_queries.py
git commit -m "feat: SearchConfig auf Projekt + Backend-Suche-Test

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend — Backend-Suche in der Projektliste

**Files:**
- Modify: `frontend/src/graphql/queries.ts` (neue Query `SEARCH_PROJEKTE`)
- Modify: `frontend/src/pages/ProjektListePage.tsx` (Debounce + Datenquelle umschalten, Client-Filter entfernen)

**Interfaces:**
- Consumes: GraphQL `search(query:, index: "global", types: ["Projekt"], pageSize: 20) { results { ... on ProjektType { ... } } total }` aus Task 2.
- Produces: keine — Endpunkt der Kette (UI).

**Hinweis zu Tests:** Kein neuer Component-Test für den Debounce/Query-Switch. Im Repo existiert
noch keine Konvention für Apollo-/Router-Component-Tests (bisherige `*.test.tsx` sind reine
Logik-Tests ohne `MockedProvider`/`MemoryRouter`); `ProjektListePage` hängt zusätzlich an
`fetch("/api/me/")` über `AuthContext`. Den Query-Vertrag selbst deckt bereits der
GraphQL-Shape-Test aus Task 2 ab (Schema-Drift-Schutz). Verifikation hier erfolgt manuell im
Dev-Server (Step 4). Neu aufsetzen, sobald eine zweite Page einen echten Component-Test braucht.

- [ ] **Step 1: Query ergänzen**

In `frontend/src/graphql/queries.ts`, nach `GET_PROJEKTE` (nach dessen schließendem Backtick)
einfügen:

```typescript
export const SEARCH_PROJEKTE = gql`
  query SearchProjekte($query: String!) {
    search(query: $query, index: "global", types: ["Projekt"], pageSize: 20) {
      results {
        ... on ProjektType {
          id
          auftragsnummer
          name
          offerteSumme {
            value
            unit
          }
          wvSumme {
            value
            unit
          }
          auftragFertig
          projektleiter
          projektKennzahlenList {
            items {
              summeWvPlus {
                value
                unit
              }
              summeIstKosten {
                value
                unit
              }
            }
          }
        }
      }
      total
    }
  }
`;
```

- [ ] **Step 2: Page umbauen**

In `frontend/src/pages/ProjektListePage.tsx`:

Import-Zeile erweitern (`useState` → zusätzlich `useEffect`):

```typescript
import { useQuery, useSubscription } from "@apollo/client/react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, ChevronsUpDown, ChevronUp, ChevronDown, Plus, Search, UserRound } from "lucide-react";
import Layout from "../components/Layout";
import { GET_PROJEKTE, SEARCH_PROJEKTE } from "../graphql/queries";
import { PROJEKT_LISTE_SUBSCRIPTION } from "../graphql/subscriptions";
import { chf, type GQLMeasurement } from "../utils/format";
import { getDeviation, DEV_STYLES } from "../utils/deviation";
import { useAuth } from "../contexts/AuthContext";
import { canCreateProject, canViewFinancials } from "../utils/permissions";
```

Nach dem bestehenden `type QueryData = { ... };` Block ein neues Typ-Alias ergänzen:

```typescript
type SearchData = {
  search: { results: Projekt[]; total: number };
};
```

Im Komponentenkörper: den Block

```typescript
  const [sortKey, setSortKey] = useState<SortKey>("auftragsnummer");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [hoveredHeader, setHoveredHeader] = useState<SortKey | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const { data, loading, error, refetch } = useQuery<QueryData>(GET_PROJEKTE, {
    fetchPolicy: "network-only",
  });

  useSubscription(PROJEKT_LISTE_SUBSCRIPTION, {
    onData: () => refetch(),
  });
```

ersetzen durch:

```typescript
  const [sortKey, setSortKey] = useState<SortKey>("auftragsnummer");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [hoveredHeader, setHoveredHeader] = useState<SortKey | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(searchQuery.trim()), 300);
    return () => clearTimeout(handle);
  }, [searchQuery]);

  const isSearching = debouncedQuery.length > 0;

  const { data, loading, error, refetch } = useQuery<QueryData>(GET_PROJEKTE, {
    fetchPolicy: "network-only",
  });

  useSubscription(PROJEKT_LISTE_SUBSCRIPTION, {
    onData: () => refetch(),
  });

  const { data: searchData, loading: searchLoading, error: searchError } = useQuery<SearchData>(
    SEARCH_PROJEKTE,
    {
      variables: { query: debouncedQuery },
      skip: !isSearching,
      fetchPolicy: "network-only",
    },
  );
```

Den Block

```typescript
  const q = searchQuery.trim().toLowerCase();
  const filtered = (data?.projektList.items ?? []).filter((p) => {
    if (!q) return true;
    return (
      p.name.toLowerCase().includes(q) ||
      p.auftragsnummer.toLowerCase().includes(q) ||
      (p.projektleiter ?? "").toLowerCase().includes(q)
    );
  });
  const items = sortProjekte(filtered, sortKey, sortDir);
  const total = data?.projektList.pageInfo.totalCount ?? 0;
```

ersetzen durch:

```typescript
  const sourceItems = isSearching
    ? (searchData?.search.results ?? [])
    : (data?.projektList.items ?? []);
  const items = sortProjekte(sourceItems, sortKey, sortDir);
  const total = isSearching
    ? (searchData?.search.total ?? 0)
    : (data?.projektList.pageInfo.totalCount ?? 0);
  const isLoading = isSearching ? searchLoading : loading;
  const displayError = isSearching ? searchError : error;
```

Weiter unten im JSX:

- `{loading && <p ...>Lade Projekte…</p>}` → `{isLoading && <p ...>Lade Projekte…</p>}`
- `{error && (...)}` Block: `error.message` → `displayError.message`, Bedingung `{error && (` →
  `{displayError && (`
- `{data && (...)}` (öffnet die Tabellen-Card): Bedingung `{data && (` → `{(isSearching ? searchData : data) && (`
- Im leeren-Zustand-Text: `{q ? (` → `{isSearching ? (` (die restlichen Referenzen auf
  `searchQuery` in diesem Block — Anzeige-Text „Kein Projekt passt zu..." — bleiben unverändert,
  sie zeigen den rohen Eingabewert, nicht den debounced Wert).
- Im Zähler-Text oben: `{q ? \`${items.length} von ${total} Projekten\` : \`${total} Projekte\`}` →
  `{isSearching ? \`${items.length} von ${total} Projekten\` : \`${total} Projekte\`}`

- [ ] **Step 3: TypeScript/Lint/Vitest laufen lassen**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/generalmanager-0-76-0-update-6899d6 forge-dev bash -lc "cd frontend && npx tsc --noEmit && npm run build && npm test"
```

Erwartet: `tsc --noEmit` ohne Fehler (Vite-Build selbst prüft Typen nicht, `vite build` nutzt
esbuild), Vite-Build ohne Fehler, bestehende Vitest-Suite weiterhin grün (keine neuen Tests in
diesem Task, s. Hinweis oben).

- [ ] **Step 4: Manuell verifizieren**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/generalmanager-0-76-0-update-6899d6 forge-dev bash -lc "uv run python manage.py runserver 0.0.0.0:8000"
```

Separates Terminal:

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/generalmanager-0-76-0-update-6899d6 forge-dev bash -lc "cd frontend && npm run dev -- --host"
```

Im Browser `http://localhost:5173/projekte` öffnen, in der Suche einen bekannten Projektnamen
eintippen: nach ~300ms erscheinen die Backend-Suchtreffer (Network-Tab zeigt eine
`SearchProjekte`-Anfrage an `/graphql/`), leeres Suchfeld zeigt wieder die volle Liste.

- [ ] **Step 5: Volles Gate laufen lassen**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/generalmanager-0-76-0-update-6899d6 forge-dev bash -lc "uv run pre-commit run --all-files"
```

Erwartet: alle Hooks `Passed`.

- [ ] **Step 6: Commit** (nur nach expliziter Freigabe)

```bash
git add frontend/src/graphql/queries.ts frontend/src/pages/ProjektListePage.tsx
git commit -m "feat: Projektliste nutzt Backend-Suche statt Client-Filter

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec-Abdeckung:**
- Backend-Auswahl dev/prod → Task 1 ✅
- Dependency `meilisearch` → Task 1 ✅
- `SearchConfig` auf `Projekt` → Task 2 ✅
- Index-Pflege (Reconcile-Settings, automatische Dirty-Markierung) → Task 1 (Settings), Rest ist
  GM-intern, kein Code nötig ✅. Einmaliger `search_index --reindex`-Deploy-Schritt ist ein
  Betriebs-/Deploy-Vorgang, kein Code-Task — nicht Teil dieses Plans (Repo hat keinen
  Deploy-Skript-Mechanismus, der hier ergänzt werden müsste; würde manuell beim ersten Rollout
  ausgeführt).
- Frontend Debounce + Query-Switch → Task 3 ✅
- Permissions automatisch über GM → keine Code-Änderung nötig, in Task 2 durch bestehende
  `Projekt.Permission` bereits abgedeckt ✅
- Testing (Backend-Test gegen DevSearch) → Task 2 ✅; Frontend-Test bewusst ausgelassen mit
  Begründung in Task 3 ✅
- Out of Scope (Filter-UI, weitere Manager-Typen, SEARCH_ASYNC, weitergehende Pagination) → in
  keinem Task enthalten ✅

**Platzhalter-Scan:** keine TBD/TODO, jeder Step trägt vollständigen Code oder einen exakten
Befehl mit erwarteter Ausgabe.

**Typ-Konsistenz:** `SearchData`/`Projekt`-Typ in Task 3 wiederverwendet den bereits in
`ProjektListePage.tsx` definierten `Projekt`-Typ (identische Feldliste wie `GET_PROJEKTE`,
bestätigt gegen die GraphQL-Query aus Task 2/Spec). `ProjektType` als Fragment-Name konsistent in
Spec, Task 2 (Backend-Test) und Task 3 (Frontend-Query) verwendet.
