# Infinite Scroll & Wegfall der Client-Sortierung (Projektliste) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET_PROJEKTE` verliert den 100er-Deckel zugunsten von Infinite Scroll (20er-Batches, serverseitig sortiert nach Auftragsnr. absteigend), die Projektliste verliert jede Klick-Sortierung, und der Suche-Index wird von `"global"` auf `"projekte"` umbenannt.

**Architecture:** Backend-Änderung ist eine Ein-Zeilen-Umbenennung (`IndexConfig.name`). Frontend: `ProjektListePage.tsx` verliert `sortProjekte()`/`SortKey`/Klick-Handler komplett, `GET_PROJEKTE` bekommt eine `$page`-Variable, ein lokaler `items`-State akkumuliert nachgeladene Seiten, ein `IntersectionObserver` auf einem Sentinel-Element am Tabellenende triggert das Nachladen über einen imperativen `client.query()`-Aufruf (bewusst nicht Apollos `fetchMore`, siehe Spec).

**Tech Stack:** Django 5 / GeneralManager 0.76.0 / GraphQL (graphene-django) / React + Apollo Client 4 / Vitest + `@testing-library/react` + `@apollo/client/testing`.

**Spec:** [docs/specs/projektliste-pagination.md](../specs/2026-08-28-projektliste-pagination.md)

## Global Constraints

- **Umgebung erkennen & wrappen (CLAUDE.md):** Backend/Frontend-Dev-Befehle (`uv`, `pytest`, `ruff`, `mypy`, `python manage.py`, `npm`, `pre-commit`) laufen im Devcontainer (`forge-dev`). Vom Host aus wrappen:
  `docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 forge-dev bash -lc "<befehl>"`
  (`-u vscode` + `bash -lc` nötig, sonst fehlen `uv`/`pre-commit` im PATH.)
- **`git commit` läuft im Container, alle anderen Git-Befehle roh auf dem Host (CLAUDE.md):** Der pre-commit-Hook braucht Dev-Tools, die nur im Container existieren. Für diesen Worktree zusätzlich `GIT_DIR`/`GIT_WORK_TREE` setzen (das `.git`-File im Worktree zeigt auf einen Host-Pfad, den der Container nicht kennt) — nötig für `git commit` **und** für `uv run pre-commit run --all-files` selbst, da `pre-commit` intern `git` aufruft (ohne die Env-Vars: `FatalError: git failed`):
  ```bash
  docker exec -u vscode \
    -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
    -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
    -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
    forge-dev bash -lc 'git commit -m "…"'
  ```
  `bash -lc` ist beim Commit zwingend (nicht nur bei `uv run ...`) — ohne Login-Shell fehlt `uv`
  im PATH und der `pre-commit`-Hook bricht mit `Executable "uv" not found` ab (live beim
  Ausführen dieses Plans aufgetreten, Task 1 Step 7). Niemals `--no-verify`. (Falls ein neu angelegter Worktree wieder einen kaputten `core.hooksPath` in seiner `config.worktree` hat: `git config --worktree --unset core.hooksPath` einmalig auf dem Host.)
- **Commit-Disziplin (CLAUDE.md):** Bei jedem Task-Commit **diese Plan-Datei mit in `git add`** aufnehmen, nachdem die Boxen des Tasks abgehakt wurden — sonst werden die Haken nie mitcommittet.
- **„Erledigt" erst, wenn das volle Gate grün ist (CLAUDE.md):** `uv run pre-commit run --all-files` (ruff, pytest, mypy, vitest) — nicht nur der einzelne Test aus dem jeweiligen Task.
- **GM-Feldzugriff** immer via `self.feldname`, nie `self._interface._instance` (GM-Skill, goldene Regel) — betrifft hier nur Task 1.
- **Frontend macht keine Validierung/Permission-Checks** (CLAUDE.md) — unverändert, diese Änderung betrifft nur Darstellung/Pagination.

---

### Task 1: Backend + Frontend — Suche-Index umbenennen `"global"` → `"projekte"`

Beide Seiten der Umbenennung gehören in einen Task/Commit, sonst ist die Suche zwischen den Commits kaputt (Frontend fragt einen Index an, den es serverseitig nicht mehr gibt).

**Files:**
- Modify: `tests/test_graphql_queries.py:119`
- Modify: `src/apps/projekt/models/projekt.py:77-87`
- Modify: `frontend/src/graphql/queries.ts:42`

**Interfaces:**
- Produces: nichts Neues — reine Umbenennung eines bestehenden Bezeichners, den Task 2/3 unverändert weiterverwenden (`SEARCH_PROJEKTE` bleibt sonst identisch).

- [x] **Step 1: Bestehenden Test auf den neuen Index-Namen umstellen (macht ihn rot)**

In `tests/test_graphql_queries.py`, Zeile 119, `_QUERY_SEARCH_PROJEKTE`:

```python
_QUERY_SEARCH_PROJEKTE = """
    query SearchProjekte($query: String!) {
      search(query: $query, index: "projekte", types: ["Projekt"], pageSize: 20) {
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

(Nur `"global"` → `"projekte"` in Zeile 119 geändert, Rest der Datei bleibt unverändert.)

- [x] **Step 2: Test laufen lassen, erwartet FAIL**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 forge-dev bash -lc "uv run pytest tests/test_graphql_queries.py::GraphQLQueryShapeTest::test_search_findet_projekt_nach_name -v"
```

Erwartet: FAIL — `Projekt.SearchConfig` registriert seine Felder noch unter `"global"`, die Suche gegen `"projekte"` findet keine registrierten Felder für diesen Index und liefert keine Treffer (`AssertionError`, `"Lueftungsanlage Nord"` fehlt in `namen`).

- [x] **Step 3: `SearchConfig` umbenennen**

In `src/apps/projekt/models/projekt.py`, Zeilen 77-87:

```python
    class SearchConfig:
        indexes = [
            IndexConfig(
                name="projekte",
                fields=[
                    "name",
                    "auftragsnummer",
                    FieldConfig(name="projektleiter__username", boost=1.5),
                ],
            )
        ]
```

(Nur `name="global"` → `name="projekte"`, Rest unverändert.)

- [x] **Step 4: Test laufen lassen, erwartet PASS**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 forge-dev bash -lc "uv run pytest tests/test_graphql_queries.py::GraphQLQueryShapeTest::test_search_findet_projekt_nach_name -v"
```

Erwartet: PASS

- [x] **Step 5: Frontend-Query mitziehen**

In `frontend/src/graphql/queries.ts`, Zeile 42, `SEARCH_PROJEKTE`:

```typescript
export const SEARCH_PROJEKTE = gql`
  query SearchProjekte($query: String!) {
    search(query: $query, index: "projekte", types: ["Projekt"], pageSize: 20) {
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

(Nur `index: "global"` → `index: "projekte"` in der ersten Zeile des Query-Bodys geändert.)

- [x] **Step 6: Volles Gate laufen lassen**

```bash
docker exec -u vscode \
  -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
  -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  forge-dev bash -lc "uv run pre-commit run --all-files"
```

Erwartet: alle fünf Hooks `Passed`. (`pre-commit run` akzeptiert nur eine einzelne Hook-ID positional, kein Filtern auf mehrere — deshalb hier der volle Lauf statt einer Teilmenge.)

- [x] **Step 7: Boxen abhaken + Commit**

Alle Boxen in Task 1 oben in dieser Datei auf `- [x]` setzen, dann:

```bash
docker exec -u vscode \
  -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
  -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  forge-dev git add tests/test_graphql_queries.py src/apps/projekt/models/projekt.py frontend/src/graphql/queries.ts docs/specs/plans/2026-08-27-projektliste-pagination.md

docker exec -u vscode \
  -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
  -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  forge-dev bash -lc 'git commit -m "feat: Suche-Index von global auf projekte umbenennen

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"'
```

(bereits ausgeführt: Commit `d05ab30`)

---

### Task 2: Frontend — Client-Sortierung entfernen, Server-Default-Sort, Summenanzeige vereinheitlichen

**Files:**
- Modify: `frontend/src/graphql/queries.ts` (`GET_PROJEKTE`)
- Modify: `frontend/src/pages/ProjektListePage.tsx`
- Create: `frontend/src/pages/ProjektListePage.test.tsx`

**Interfaces:**
- Consumes: `GET_PROJEKTE` liefert weiterhin `projektList(pageSize: Int, sortBy: [ProjektSortByOptions!], reverse: Boolean) { items {...} pageInfo { totalCount } }` — hier noch ohne `page`-Variable (kommt in Task 3).
- Produces: `ProjektListePage` rendert Tabellen-Header ohne `onClick`/Sortier-Icon; ein neuer Test-Aufbau (`MockedProvider` + Auth-Mock) in `ProjektListePage.test.tsx`, den Task 3 erweitert statt neu zu bauen.

- [x] **Step 1: `GET_PROJEKTE` um Server-Default-Sort ergänzen**

In `frontend/src/graphql/queries.ts`, `GET_PROJEKTE` (Zeile 3-38), die erste Zeile im Query-Body:

```typescript
export const GET_PROJEKTE = gql`
  query ProjektListe {
    projektList(pageSize: 100, sortBy: [auftragsnummer], reverse: true) {
      items {
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
      pageInfo {
        totalCount
      }
    }
  }
`;
```

(Nur `projektList(pageSize: 100)` → `projektList(pageSize: 100, sortBy: [auftragsnummer], reverse: true)`, Rest unverändert. `pageSize` bleibt bewusst bei 100 — wird erst in Task 3 auf 20 reduziert, wenn Infinite Scroll den Ausgleich schafft.)

- [x] **Step 2: Failing Test schreiben**

Neue Datei `frontend/src/pages/ProjektListePage.test.tsx`:

```tsx
import { MemoryRouter } from "react-router-dom";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { describe, expect, it, vi } from "vitest";

import ProjektListePage from "./ProjektListePage";
import { GET_PROJEKTE } from "../graphql/queries";
import { PROJEKT_LISTE_SUBSCRIPTION } from "../graphql/subscriptions";

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, username: "admin", groups: ["Admin"], isStaff: true },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

function projekt(overrides: Record<string, unknown> = {}) {
  return {
    id: "1",
    auftragsnummer: "T-2026-002",
    name: "Bauprojekt B",
    offerteSumme: { value: 10000, unit: "CHF" },
    wvSumme: { value: 9000, unit: "CHF" },
    auftragFertig: false,
    projektleiter: "Max Muster",
    projektKennzahlenList: {
      items: [{ summeWvPlus: { value: 9500, unit: "CHF" }, summeIstKosten: { value: 8000, unit: "CHF" } }],
    },
    ...overrides,
  };
}

const listeMock = {
  request: { query: GET_PROJEKTE },
  result: {
    data: {
      projektList: {
        items: [
          projekt({ id: "1", auftragsnummer: "T-2026-002", name: "Bauprojekt B" }),
          projekt({ id: "2", auftragsnummer: "T-2026-001", name: "Aufbauprojekt A" }),
        ],
        pageInfo: { totalCount: 2 },
      },
    },
  },
};

const subscriptionMock = {
  request: { query: PROJEKT_LISTE_SUBSCRIPTION },
  result: { data: { onProjektClassChange: { action: "noop" } } },
  delay: 1000 * 60 * 60,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <MockedProvider mocks={[listeMock, subscriptionMock]}>
        <ProjektListePage />
      </MockedProvider>
    </MemoryRouter>,
  );
}

describe("ProjektListePage – keine Client-Sortierung mehr", () => {
  it("Klick auf einen Spalten-Header ändert die Reihenfolge nicht", async () => {
    renderPage();
    await screen.findByText("Bauprojekt B");

    const rowsBefore = screen.getAllByRole("row").slice(1);
    expect(within(rowsBefore[0]).getByText("Bauprojekt B")).toBeInTheDocument();
    expect(within(rowsBefore[1]).getByText("Aufbauprojekt A")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Name"));

    const rowsAfter = screen.getAllByRole("row").slice(1);
    expect(within(rowsAfter[0]).getByText("Bauprojekt B")).toBeInTheDocument();
    expect(within(rowsAfter[1]).getByText("Aufbauprojekt A")).toBeInTheDocument();
  });

  it("zeigt die Summe im einheitlichen Format neben dem Suchfeld", async () => {
    renderPage();
    const total = await screen.findByText("2 von 2 Projekten");
    const searchInput = screen.getByPlaceholderText(/Suche nach Name/i);
    // eslint-disable-next-line no-bitwise
    expect(
      total.compareDocumentPosition(searchInput) & Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeTruthy();
  });
});
```

- [x] **Step 3: Tests laufen lassen, erwartet FAIL**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373/frontend forge-dev bash -lc "npx vitest run src/pages/ProjektListePage.test.tsx"
```

Erwartet: FAIL — die aktuelle Komponente zeigt "2 Projekte" statt "2 von 2 Projekten" (Listenmodus-Sonderformulierung) und die Summe steht noch in der `<h1>`-Kopfzeile statt neben dem Suchfeld; der Sortier-Test schlägt ebenfalls fehl, weil ein Klick auf "Name" die Reihenfolge aktuell noch ändert.

- [x] **Step 4: `ProjektListePage.tsx` umbauen — Sortierung raus, Summe verschieben**

Import-Zeile (Zeile 4):

```typescript
import { ChevronRight, Plus, Search, UserRound } from "lucide-react";
```

Typen-Block (Zeilen 32-35) — `SortKey`/`SortDir`/`DESC_DEFAULT` komplett entfernen (nicht ersetzen, nur löschen):

```typescript
// gelöscht: SortKey, SortDir, DESC_DEFAULT
```

Funktion `SortIcon` (Zeilen 125-132) komplett löschen.

Funktion `sortProjekte` (Zeilen 134-155) komplett löschen.

Im Komponentenkörper, den Block (Zeilen 163-192, State-Deklarationen bis `handleSort`):

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

  const {
    data: searchData,
    loading: searchLoading,
    error: searchError,
  } = useQuery<SearchData>(SEARCH_PROJEKTE, {
    variables: { query: debouncedQuery },
    skip: !isSearching,
    fetchPolicy: "network-only",
  });

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(DESC_DEFAULT.has(key) ? "desc" : "asc");
    }
  }

  const sourceItems = isSearching
    ? (searchData?.search.results ?? [])
    : (data?.projektList.items ?? []);
  const items = sortProjekte(sourceItems, sortKey, sortDir);
  const total = isSearching
    ? (searchData?.search.total ?? 0)
    : (data?.projektList.pageInfo.totalCount ?? 0);
  const isLoading = isSearching ? searchLoading : loading;
  const displayError = isSearching ? searchError : error;

  const thBase = (key: SortKey) =>
    `px-4 py-3 text-[11px] uppercase tracking-wider font-semibold select-none cursor-pointer transition-colors whitespace-nowrap ${
      sortKey === key ? "text-blue-700" : "text-gray-500 hover:text-gray-900"
    }`;
```

ersetzen durch:

```typescript
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

  const {
    data: searchData,
    loading: searchLoading,
    error: searchError,
  } = useQuery<SearchData>(SEARCH_PROJEKTE, {
    variables: { query: debouncedQuery },
    skip: !isSearching,
    fetchPolicy: "network-only",
  });

  const items = isSearching
    ? (searchData?.search.results ?? [])
    : (data?.projektList.items ?? []);
  const total = isSearching
    ? (searchData?.search.total ?? 0)
    : (data?.projektList.pageInfo.totalCount ?? 0);
  const isLoading = isSearching ? searchLoading : loading;
  const displayError = isSearching ? searchError : error;
```

- [x] **Step 5: Kopfzeile — Summentext raus aus der `<h1>`-Zeile**

Den Block (im Original Zeilen 220-241):

```tsx
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-[22px] font-semibold text-gray-900">Projekte</h1>
          {data && (
            <p className="text-[12px] text-gray-500 mt-0.5">
            {isSearching ? `${items.length} von ${total} Projekten` : `${total} Projekte`}
          </p>
          )}
        </div>
```

ersetzen durch:

```tsx
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-[22px] font-semibold text-gray-900">Projekte</h1>
        </div>
```

- [x] **Step 6: Suchfeld-Zeile — Summe daneben anzeigen**

Den Block (im Original Zeilen 256-278):

```tsx
          <div className="px-4 py-3 border-b border-gray-200">
            <div className="relative max-w-sm">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
              <input
                type="text"
                placeholder="Suche nach Name, Auftragsnr. oder Projektleiter…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-8 py-2 text-sm rounded-md border border-gray-200 bg-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                  aria-label="Suche zurücksetzen"
                >
                  ×
                </button>
              )}
            </div>
          </div>
```

ersetzen durch:

```tsx
          <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-4">
            <div className="relative max-w-sm flex-1">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
              <input
                type="text"
                placeholder="Suche nach Name, Auftragsnr. oder Projektleiter…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-8 py-2 text-sm rounded-md border border-gray-200 bg-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                  aria-label="Suche zurücksetzen"
                >
                  ×
                </button>
              )}
            </div>
            <p className="text-[12px] text-gray-500 whitespace-nowrap">
              {items.length} von {total} Projekten
            </p>
          </div>
```

- [x] **Step 7: Tabellen-Header — statische Labels statt Klick-Sortierung**

Den Block (im Original Zeilen 345-402, `<thead>...</thead>`):

```tsx
              <thead>
                <tr className="border-b border-gray-200 text-left">
                  <th
                    className={thBase("auftragsnummer")}
                    onClick={() => handleSort("auftragsnummer")}
                    onMouseEnter={() => setHoveredHeader("auftragsnummer")}
                    onMouseLeave={() => setHoveredHeader(null)}
                  >
                    Auftragsnr.
                    <SortIcon active={sortKey === "auftragsnummer"} dir={sortDir} hovered={hoveredHeader === "auftragsnummer"} />
                  </th>
                  <th
                    className={thBase("name")}
                    onClick={() => handleSort("name")}
                    onMouseEnter={() => setHoveredHeader("name")}
                    onMouseLeave={() => setHoveredHeader(null)}
                  >
                    Name
                    <SortIcon active={sortKey === "name"} dir={sortDir} hovered={hoveredHeader === "name"} />
                  </th>
                  <th
                    className={thBase("projektleiter")}
                    onClick={() => handleSort("projektleiter")}
                    onMouseEnter={() => setHoveredHeader("projektleiter")}
                    onMouseLeave={() => setHoveredHeader(null)}
                  >
                    Projektleiter
                    <SortIcon active={sortKey === "projektleiter"} dir={sortDir} hovered={hoveredHeader === "projektleiter"} />
                  </th>
                  {showFinancials && (
                    <>
                      <th
                        className={`${thBase("offerteSumme")} text-right`}
                        onClick={() => handleSort("offerteSumme")}
                        onMouseEnter={() => setHoveredHeader("offerteSumme")}
                        onMouseLeave={() => setHoveredHeader(null)}
                      >
                        Offerte
                        <SortIcon active={sortKey === "offerteSumme"} dir={sortDir} hovered={hoveredHeader === "offerteSumme"} />
                      </th>
                      <th
                        className={`${thBase("summeWvPlus")} text-right`}
                        onClick={() => handleSort("summeWvPlus")}
                        onMouseEnter={() => setHoveredHeader("summeWvPlus")}
                        onMouseLeave={() => setHoveredHeader(null)}
                      >
                        WV + Zusätze
                        <SortIcon active={sortKey === "summeWvPlus"} dir={sortDir} hovered={hoveredHeader === "summeWvPlus"} />
                      </th>
                      <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500">
                        Abweichung zu Ist
                      </th>
                    </>
                  )}
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500">
                    Status
                  </th>
                </tr>
              </thead>
```

ersetzen durch:

```tsx
              <thead>
                <tr className="border-b border-gray-200 text-left">
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500">
                    Auftragsnr.
                  </th>
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500">
                    Name
                  </th>
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500">
                    Projektleiter
                  </th>
                  {showFinancials && (
                    <>
                      <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-right">
                        Offerte
                      </th>
                      <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-right">
                        WV + Zusätze
                      </th>
                      <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500">
                        Abweichung zu Ist
                      </th>
                    </>
                  )}
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500">
                    Status
                  </th>
                </tr>
              </thead>
```

- [x] **Step 8: Leerer-Zustand-Text — `q` durch `isSearching` ersetzen**

Im Original nutzt der Leer-Zustand-Block bereits `{isSearching ? (` (das war schon in der Vorgänger-Spec so umgestellt, siehe `git log` für `queries.ts`/`ProjektListePage.tsx`) — falls beim Lesen der aktuellen Datei stattdessen noch `{q ? (` auftaucht: auf `{isSearching ? (` ändern. Sonst diesen Step überspringen (nichts zu tun).

- [x] **Step 9: Tests laufen lassen, erwartet PASS**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373/frontend forge-dev bash -lc "npx vitest run src/pages/ProjektListePage.test.tsx"
```

Erwartet: PASS (beide Tests).

- [x] **Step 10: TypeScript/Build prüfen**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373/frontend forge-dev bash -lc "npx tsc --noEmit"
```

Erwartet: keine Fehler (insbesondere kein `SortKey`/`sortProjekte` mehr referenziert).

- [x] **Step 11: Volles Gate laufen lassen**

```bash
docker exec -u vscode \
  -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
  -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  forge-dev bash -lc "uv run pre-commit run --all-files"
```

Erwartet: alle fünf Hooks `Passed`.

- [x] **Step 12: Boxen abhaken + Commit**

Alle Boxen in Task 2 oben in dieser Datei auf `- [x]` setzen, dann:

```bash
docker exec -u vscode \
  -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
  -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  forge-dev git add frontend/src/graphql/queries.ts frontend/src/pages/ProjektListePage.tsx frontend/src/pages/ProjektListePage.test.tsx docs/specs/plans/2026-08-27-projektliste-pagination.md

docker exec -u vscode \
  -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
  -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  forge-dev bash -lc 'git commit -m "feat: Klick-Sortierung aus Projektliste entfernen, Server-Default-Sort

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"'
```

---

### Task 3: Frontend — Infinite Scroll für `GET_PROJEKTE`

**Files:**
- Modify: `frontend/src/graphql/queries.ts` (`GET_PROJEKTE`)
- Modify: `frontend/src/pages/ProjektListePage.tsx`
- Modify: `frontend/src/pages/ProjektListePage.test.tsx`

**Interfaces:**
- Consumes: `GET_PROJEKTE($page: Int!)` aus Task 2, jetzt mit `page`-Variable statt fixem `pageSize: 100`.
- Produces: Endpunkt der Kette (UI) — nichts, das weitere Tasks konsumieren.

- [x] **Step 1: `GET_PROJEKTE` bekommt `$page` + `pageSize: 20`**

In `frontend/src/graphql/queries.ts`, `GET_PROJEKTE`, die ersten zwei Zeilen:

```typescript
export const GET_PROJEKTE = gql`
  query ProjektListe($page: Int!) {
    projektList(page: $page, pageSize: 20, sortBy: [auftragsnummer], reverse: true) {
```

(Rest von `GET_PROJEKTE` — die `items { ... } pageInfo { totalCount }`-Felder — unverändert aus Task 2 übernehmen.)

- [x] **Step 2: Failing Tests schreiben — bestehende Mocks + zwei neue Tests**

In `frontend/src/pages/ProjektListePage.test.tsx`: Import-Block und Hilfsfunktionen erweitern.

Import-Zeile ergänzen:

```tsx
import { ApolloLink } from "@apollo/client/link";
import { getMainDefinition } from "@apollo/client/utilities";
import { MockLink, MockSubscriptionLink } from "@apollo/client/testing";
```

Den Block `listeMock` (aus Task 2) ersetzen durch:

```typescript
const listePage1Mock = {
  request: { query: GET_PROJEKTE, variables: { page: 1 } },
  result: {
    data: {
      projektList: {
        items: [
          projekt({ id: "1", auftragsnummer: "T-2026-002", name: "Bauprojekt B" }),
          projekt({ id: "2", auftragsnummer: "T-2026-001", name: "Aufbauprojekt A" }),
        ],
        pageInfo: { totalCount: 2 },
      },
    },
  },
};
```

`renderPage()` (aus Task 2) — Referenz auf `listeMock` durch `listePage1Mock` ersetzen:

```typescript
function renderPage() {
  return render(
    <MemoryRouter>
      <MockedProvider mocks={[listePage1Mock, subscriptionMock]}>
        <ProjektListePage />
      </MockedProvider>
    </MemoryRouter>,
  );
}
```

Neuen Helper + IntersectionObserver-Mock nach den bestehenden Konstanten (`subscriptionMock`) ergänzen:

```typescript
let intersectionCallback: (entries: Pick<IntersectionObserverEntry, "isIntersecting">[]) => void = () => {};

class FakeIntersectionObserver {
  constructor(callback: typeof intersectionCallback) {
    intersectionCallback = callback;
  }
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = () => [];
  root = null;
  rootMargin = "";
  thresholds: number[] = [];
}

// @ts-expect-error -- jsdom kennt IntersectionObserver nicht, Fake reicht für die Tests
global.IntersectionObserver = FakeIntersectionObserver;

function renderWithControlledSubscription(mocks: MockLink.MockedResponse[]) {
  const subscriptionLink = new MockSubscriptionLink();
  const queryLink = new MockLink(mocks, { showWarnings: false });
  const link = ApolloLink.split(
    ({ query }) => {
      const def = getMainDefinition(query);
      return def.kind === "OperationDefinition" && def.operation === "subscription";
    },
    subscriptionLink,
    queryLink,
  );
  const utils = render(
    <MemoryRouter>
      <MockedProvider link={link}>
        <ProjektListePage />
      </MockedProvider>
    </MemoryRouter>,
  );
  return { ...utils, subscriptionLink };
}
```

Neue `describe`-Blöcke am Ende der Datei ergänzen:

```typescript
describe("ProjektListePage – Infinite Scroll", () => {
  it("lädt beim Erreichen des Sentinels die nächste Seite nach und hängt sie an", async () => {
    const page1 = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [
              projekt({ id: "1", auftragsnummer: "T-2026-003", name: "Projekt Eins" }),
              projekt({ id: "2", auftragsnummer: "T-2026-002", name: "Projekt Zwei" }),
            ],
            pageInfo: { totalCount: 3 },
          },
        },
      },
    };
    const page2 = {
      request: { query: GET_PROJEKTE, variables: { page: 2 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "3", auftragsnummer: "T-2026-001", name: "Projekt Drei" })],
            pageInfo: { totalCount: 3 },
          },
        },
      },
    };

    render(
      <MemoryRouter>
        <MockedProvider mocks={[page1, page2, subscriptionMock]}>
          <ProjektListePage />
        </MockedProvider>
      </MemoryRouter>,
    );

    await screen.findByText("Projekt Eins");
    expect(screen.queryByText("Projekt Drei")).not.toBeInTheDocument();

    intersectionCallback([{ isIntersecting: true }]);

    await screen.findByText("Projekt Drei");
    expect(screen.getByText("Projekt Eins")).toBeInTheDocument();
    expect(screen.getByText("Projekt Zwei")).toBeInTheDocument();
  });

  it("setzt bei einem Live-Update auf Seite 1 zurück und verwirft nachgeladene Seiten", async () => {
    const page1 = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "1", auftragsnummer: "T-2026-002", name: "Vor Update" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
    };
    const page2 = {
      request: { query: GET_PROJEKTE, variables: { page: 2 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "2", auftragsnummer: "T-2026-001", name: "Seite Zwei" })],
            pageInfo: { totalCount: 2 },
          },
        },
      },
    };
    const page1NachUpdate = {
      request: { query: GET_PROJEKTE, variables: { page: 1 } },
      result: {
        data: {
          projektList: {
            items: [projekt({ id: "3", auftragsnummer: "T-2026-003", name: "Nach Update" })],
            pageInfo: { totalCount: 1 },
          },
        },
      },
    };

    const { subscriptionLink } = renderWithControlledSubscription([page1, page2, page1NachUpdate]);

    await screen.findByText("Vor Update");
    intersectionCallback([{ isIntersecting: true }]);
    await screen.findByText("Seite Zwei");

    subscriptionLink.simulateResult({
      result: { data: { onProjektClassChange: { action: "updated" } } },
    });

    await screen.findByText("Nach Update");
    expect(screen.queryByText("Vor Update")).not.toBeInTheDocument();
    expect(screen.queryByText("Seite Zwei")).not.toBeInTheDocument();
  });
});
```

- [x] **Step 3: Tests laufen lassen, erwartet FAIL**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373/frontend forge-dev bash -lc "npx vitest run src/pages/ProjektListePage.test.tsx"
```

Erwartet: die beiden Task-2-Tests FAIL (Mock erwartet jetzt `variables: { page: 1 }`, Komponente fragt noch ohne `page`-Variable an), die beiden neuen Infinite-Scroll-Tests FAIL (Komponente hat noch keinen Sentinel/kein Nachladen).

- [x] **Step 4: `ProjektListePage.tsx` — Infinite Scroll implementieren**

Import-Zeile:

```typescript
import { useApolloClient, useQuery, useSubscription } from "@apollo/client/react";
import { useEffect, useRef, useState } from "react";
```

Im Komponentenkörper, den Block aus Task 2 (State-Deklarationen bis `displayError`):

```typescript
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

  const {
    data: searchData,
    loading: searchLoading,
    error: searchError,
  } = useQuery<SearchData>(SEARCH_PROJEKTE, {
    variables: { query: debouncedQuery },
    skip: !isSearching,
    fetchPolicy: "network-only",
  });

  const items = isSearching
    ? (searchData?.search.results ?? [])
    : (data?.projektList.items ?? []);
  const total = isSearching
    ? (searchData?.search.total ?? 0)
    : (data?.projektList.pageInfo.totalCount ?? 0);
  const isLoading = isSearching ? searchLoading : loading;
  const displayError = isSearching ? searchError : error;
```

ersetzen durch:

```typescript
  const client = useApolloClient();
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [listItems, setListItems] = useState<Projekt[]>([]);
  const [loadedPage, setLoadedPage] = useState(1);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLTableRowElement | null>(null);

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(searchQuery.trim()), 300);
    return () => clearTimeout(handle);
  }, [searchQuery]);

  const isSearching = debouncedQuery.length > 0;

  const { data, loading, error, refetch } = useQuery<QueryData>(GET_PROJEKTE, {
    variables: { page: 1 },
    fetchPolicy: "network-only",
  });

  useEffect(() => {
    if (data) {
      setListItems(data.projektList.items);
      setLoadedPage(1);
    }
  }, [data]);

  useSubscription(PROJEKT_LISTE_SUBSCRIPTION, {
    onData: () => refetch({ page: 1 }),
  });

  const {
    data: searchData,
    loading: searchLoading,
    error: searchError,
  } = useQuery<SearchData>(SEARCH_PROJEKTE, {
    variables: { query: debouncedQuery },
    skip: !isSearching,
    fetchPolicy: "network-only",
  });

  const items = isSearching ? (searchData?.search.results ?? []) : listItems;
  const total = isSearching
    ? (searchData?.search.total ?? 0)
    : (data?.projektList.pageInfo.totalCount ?? 0);
  const isLoading = isSearching ? searchLoading : loading;
  const displayError = isSearching ? searchError : error;

  useEffect(() => {
    if (isSearching) return;
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) loadMore();
    });
    observer.observe(sentinel);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSearching, listItems.length, total, loadingMore]);

  function loadMore() {
    if (loadingMore || isSearching || listItems.length >= total) return;
    const nextPage = loadedPage + 1;
    setLoadingMore(true);
    client
      .query<QueryData>({
        query: GET_PROJEKTE,
        variables: { page: nextPage },
        fetchPolicy: "network-only",
      })
      .then((res) => {
        if (!res.data) return; // Apollo-v4-Typing: client.query() liefert data als optional
        const newItems = res.data.projektList.items;
        setListItems((prev) => [...prev, ...newItems]);
        setLoadedPage(nextPage);
      })
      .finally(() => setLoadingMore(false));
  }
```

- [x] **Step 5: Sentinel-Zeile in der Tabelle ergänzen**

Den Block (Ende von `<tbody>`, direkt nach `{items.map((p) => (...))}`):

```tsx
              <tbody>
                {items.map((p) => (
```

Das schließende `</tbody>` (direkt nach dem `))}` von `items.map`) — den Block

```tsx
                ))}
              </tbody>
```

ersetzen durch:

```tsx
                ))}
                {!isSearching && listItems.length < total && (
                  <tr ref={sentinelRef}>
                    <td
                      colSpan={showFinancials ? 7 : 4}
                      className="px-4 py-3 text-center text-xs text-gray-400"
                    >
                      {loadingMore ? "Lade weitere Projekte…" : ""}
                    </td>
                  </tr>
                )}
              </tbody>
```

- [x] **Step 6: Tests laufen lassen, erwartet PASS**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373/frontend forge-dev bash -lc "npx vitest run src/pages/ProjektListePage.test.tsx"
```

Erwartet: alle vier Tests PASS.

- [x] **Step 7: TypeScript/Build prüfen**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373/frontend forge-dev bash -lc "npx tsc --noEmit && npm run build"
```

Erwartet: keine Typfehler, Build erfolgreich.

- [x] **Step 8: Manuell verifizieren**

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 forge-dev bash -lc "uv run python manage.py runserver 0.0.0.0:8000"
```

Separates Terminal:

```bash
docker exec -u vscode -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373/frontend forge-dev bash -lc "npm run dev -- --host"
```

Im Browser `http://localhost:5173/projekte` öffnen: Liste zeigt max. 20 Zeilen, sortiert nach Auftragsnr. absteigend, Summe steht neben dem Suchfeld; runterscrollen lädt weitere 20 nach (Network-Tab zeigt eine zweite `ProjektListe`-Anfrage mit `page: 2`); Klick auf einen Spalten-Header ändert nichts.

- [x] **Step 9: Volles Gate laufen lassen**

```bash
docker exec -u vscode \
  -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
  -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  forge-dev bash -lc "uv run pre-commit run --all-files"
```

Erwartet: alle fünf Hooks `Passed`.

- [x] **Step 10: Boxen abhaken + Commit**

Alle Boxen in Task 3 oben in dieser Datei auf `- [x]` setzen, dann:

```bash
docker exec -u vscode \
  -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
  -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  forge-dev git add frontend/src/graphql/queries.ts frontend/src/pages/ProjektListePage.tsx frontend/src/pages/ProjektListePage.test.tsx docs/specs/plans/2026-08-27-projektliste-pagination.md

docker exec -u vscode \
  -e GIT_DIR=/workspaces/Forge/.git/worktrees/projektliste-graphql-query-aaa373 \
  -e GIT_WORK_TREE=/workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  -w /workspaces/Forge/.claude/worktrees/projektliste-graphql-query-aaa373 \
  forge-dev bash -lc 'git commit -m "feat: Infinite Scroll für die Projektliste (GET_PROJEKTE)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"'
```

---

## Self-Review

**Spec-Abdeckung:**
- Backend-Index-Umbenennung → Task 1 ✅ (inkl. Korrektur des bestehenden Backend-Tests, den die Spec ursprünglich übersehen hatte)
- Keine User-Sortierung mehr, Standard-Sort serverseitig → Task 2 ✅
- Summenanzeige neben Suchfeld, einheitlicher Text → Task 2 ✅
- Infinite Scroll nur für `GET_PROJEKTE`, `SEARCH_PROJEKTE` unverändert → Task 3 ✅
- Live-Update setzt auf Seite 1 zurück, verwirft nachgeladene Seiten → Task 3 ✅
- `fetchMore` bewusst vermieden, imperativer `client.query()` → Task 3 ✅
- Reindex-Deploy-Hinweis aus der Spec → kein Code-Task (Ops-Schritt), separat im Rollout auszuführen, nicht Teil dieses Plans (analog zur Vorgänger-Spec, die den gleichen Meilisearch-Rollout-Schritt genauso behandelt hat).

**Platzhalter-Scan:** keine TBD/TODO, jeder Step trägt vollständigen Code oder einen exakten Befehl mit erwarteter Ausgabe.

**Typ-Konsistenz:** `Projekt`/`QueryData`/`SearchData`-Typen unverändert aus der bestehenden Datei übernommen (keine neuen Typen nötig). `listItems`-State (Task 3) ersetzt die reine `items`-Konstante aus Task 2 für den Nicht-Such-Fall; `items` bleibt der nach außen sichtbare, im JSX verwendete Name in beiden Tasks. Testdatei-Helfer `projekt()` und `subscriptionMock` aus Task 2 werden in Task 3 unverändert weiterverwendet, `listeMock` aus Task 2 wird in Task 3 explizit durch `listePage1Mock` ersetzt (Namensänderung dokumentiert in Task 3 Step 2).

## Nachtrag (Code-Review nach Task 3)

Die PR-Review deckte zwei Lücken im `loadMore()`/Reset-Zusammenspiel aus Task 3 Step 4 auf, die
in den obigen Code-Blöcken (Stand: Ausführung) noch nicht enthalten sind:

- **Race Condition beim Reset:** Löst ein Live-Update (`onData` → `refetch({ page: 1 })`) einen
  Reset aus, während ein `loadMore()`-`client.query()` für eine höhere Seite noch aussteht, hängt
  dessen `.then()`-Callback die veraltete Seite unkontrolliert an die frisch zurückgesetzte Liste
  an. Fix: ein `requestGenerationRef`-Zähler wird bei jedem Reset erhöht; `loadMore()` merkt sich
  die Generation zum Startzeitpunkt und verwirft sein Ergebnis, falls sich die Generation bis zur
  Antwort geändert hat.
- **Fehlender Fehler-/Retry-Pfad:** `client.query()` hatte kein `.catch()` — ein Reject wurde zum
  unhandled rejection, `displayError` blieb `null`, es gab keinen Retry außer zufälligem
  Neu-Triggern durch den `IntersectionObserver`. Fix: neuer `loadMoreError`-State, gefüllt über
  `.catch()`, fließt in `displayError` ein (`error ?? loadMoreError`); die Sentinel-Zeile zeigt bei
  gesetztem Fehler statt "Lade weitere Projekte…" einen Retry-Button, der `loadMore()` erneut
  aufruft; der `IntersectionObserver`-Effekt löst währenddessen kein automatisches Nachladen aus
  (`!loadMoreError`-Guard).

Beide Fixes plus zwei neue Tests (verspätete Seite-2-Antwort nach Live-Update; Retry nach
Fehler) sind im tatsächlichen Code (`frontend/src/pages/ProjektListePage.tsx`,
`ProjektListePage.test.tsx`) umgesetzt — die Code-Blöcke oben in Task 3 Step 4 spiegeln den
Stand vor diesem Nachtrag und wurden nicht rückwirkend umgeschrieben, um den Ausführungsverlauf
nicht zu verfälschen.
