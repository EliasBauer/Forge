# Spec: Infinite Scroll & Wegfall der Client-Sortierung für die Projektliste

## Ziel

`ProjektListePage.tsx` lädt Projekte aktuell über einen harten `pageSize`-Deckel
(`GET_PROJEKTE`: 100, `SEARCH_PROJEKTE`: 20) und sortiert clientseitig über die geladenen
Zeilen (`sortProjekte`). Bei ~50 Projekten heute und ca. +20/Jahr wird der 100er-Deckel in
2–3 Jahren real: zusätzliche Projekte tauchen dann einfach nicht mehr in der Liste auf.

Diese Spec ersetzt den festen Deckel bei `GET_PROJEKTE` durch Infinite Scroll (20er-Batches,
serverseitig sortiert nach Auftragsnr. absteigend) und entfernt die klickbare
Spalten-Sortierung vollständig. `SEARCH_PROJEKTE` bleibt inhaltlich unverändert (feste
`pageSize: 20`, kein Nachladen) — Suchergebnisse sind erfahrungsgemäß klein genug, dass ein
Cap dort unkritisch ist.

## Ist-Zustand

- `GET_PROJEKTE` ([queries.ts:3-38](../../frontend/src/graphql/queries.ts#L3-L38)):
  `projektList(pageSize: 100)`, kein `page`-Arg, kein `sortBy`.
- `SEARCH_PROJEKTE` ([queries.ts:40-75](../../frontend/src/graphql/queries.ts#L40-L75)):
  `search(query: $query, index: "global", types: ["Projekt"], pageSize: 20)`, kein `page`-Arg.
- `sortProjekte()` ([ProjektListePage.tsx:134](../../frontend/src/pages/ProjektListePage.tsx#L134)):
  reines Client-Array-Sort über die jeweils geladene Ergebnismenge. 5 Spalten sind heute
  klickbar sortierbar: Auftragsnr., Name, Projektleiter, Offerte (`offerteSumme`), WV +
  Zusätze (`summeWvPlus`).
- Kopfzeile zeigt heute im Suchmodus `"{items.length} von {total} Projekten"`, im Listenmodus
  nur `"{total} Projekte"` — unter der `<h1>`, nicht neben dem Suchfeld.
- Initial-Load bleibt bewusst über `GET_PROJEKTE`, nicht `SEARCH_PROJEKTE` — das ist die
  einzige Query, die an `PROJEKT_LISTE_SUBSCRIPTION` hängt (Live-Update bei Änderungen durch
  Kolleg:innen). Diese Trennung ist unverändert korrekt und **nicht** Teil dieser Spec.
- Der Suche-Index heißt aktuell `"global"` ([projekt.py:80](../../src/apps/projekt/models/projekt.py#L80))
  — einzige Fundstelle im Repo (Backend-Config + Frontend-Query).

## Backend-Fähigkeiten (verifiziert gegen GM v0.76.0 Quellcode)

- `projektList` unterstützt `page`, `pageSize`, `sort_by` (Liste von
  `{ManagerName}SortByOptions`-Enum-Werten) und `reverse: Boolean`, sowie
  `pageInfo { totalCount totalPages currentPage pageSize }` ([graphql.py](../../.venv/lib/python3.12/site-packages/general_manager/api/graphql.py)).
  Reine String-`orderBy`-Args gibt es in dieser Version **nicht** — GraphQL-seitig sind
  Enum-Werte, keine Strings, zu verwenden (unquoted, Python-Attributname z. B.
  `auftragsnummer`). `reverse: true` kehrt die (aufsteigende) Standardrichtung des
  gewählten Sortierfelds um.
- `search` unterstützt `page`, `page_size` sowie `total` im Ergebnis
  ([graphql_search.py](../../.venv/lib/python3.12/site-packages/general_manager/api/graphql_search.py)).
  `sort_by`/`sort_desc` existieren ebenfalls, werden hier aber nicht verwendet, da die Suche
  keine User-Sortierung mehr braucht (sortiert weiterhin nach Relevanz-Score).
- `types: ["Projekt"]` im `search`-Aufruf ist kein Boilerplate, sondern grenzt die Suche
  gezielt auf den `Projekt`-Manager ein. Ohne `types` durchsucht der Resolver **alle**
  Manager mit `SearchConfig` und liefert eine Union zurück; die Frontend-Query hat aber nur
  ein `... on ProjektType`-Fragment. Käme künftig ein zweiter suchbarer Manager hinzu, gäbe
  es ohne `types`-Filter Treffer, für die kein Fragment matcht (leere Felder). Bleibt daher
  unverändert bestehen.
- Der `IndexConfig.name` ist zugleich die physische Meilisearch-Index-UID
  ([backends/meilisearch.py](../../.venv/lib/python3.12/site-packages/general_manager/search/backends/meilisearch.py)).
  Eine Umbenennung ändert also den tatsächlichen Index, nicht nur ein Label — nach dem Deploy
  ist ein Reindex nötig (siehe unten).
- Ein Test referenziert `index="global"` explizit: `tests/test_graphql_queries.py:119`
  (`_QUERY_SEARCH_PROJEKTE`). Muss im selben Zug auf `"projekte"` mitgezogen werden, sonst
  bricht ein bislang grüner Test (frühere Aussage in dieser Spec, dass kein Test betroffen
  sei, war falsch — die Suche war auf `src/` beschränkt, `tests/` liegt aber auf Repo-Root-Ebene).

## Entscheidung: Keine User-Sortierung mehr

Alle 5 Spalten (Auftragsnr., Name, Projektleiter, Offerte, WV + Zusätze) verlieren Klick,
Hover-State und Sortier-Icon. Header werden reine Text-Labels wie die bestehenden
"Status"/"Abweichung zu Ist"-Header. Grund: die serverseitige Sortierbarkeit ist über die
Spalten hinweg uneinheitlich (Geld-Spalten sind teils gar nicht, teils nur in einem der
beiden Modi sortierbar — Details dazu in der vorherigen Iteration dieser Spec), und der
Product-Owner-Entscheid ist, Sortierung komplett zu entfernen statt Inkonsistenz zu managen.

**Standard-Sortierung bleibt bestehen:** Auftragsnr. absteigend, jetzt aber serverseitig
über `sortBy: [auftragsnummer], reverse: true` statt clientseitig.

`SortKey`, `SortDir`, `SortIcon`, `sortProjekte()`, `handleSort`, `hoveredHeader`, `thBase`
und `DESC_DEFAULT` werden komplett aus `ProjektListePage.tsx` entfernt.

## Backend-Änderung

Einzige Änderung in [projekt.py](../../src/apps/projekt/models/projekt.py): Index umbenennen.

```python
class SearchConfig:
    indexes = [
        IndexConfig(
            name="projekte",  # war "global" — kein sprechender Name
            fields=["name", "auftragsnummer", FieldConfig(name="projektleiter__username", boost=1.5)],
        )
    ]
```

Kein `sorts`-Feld nötig — die Suche sortiert weiterhin nur nach Relevanz.

**Deployment-Hinweis (kein Code, aber Teil des Rollouts):** nach dem Deploy muss der neue
Index befüllt werden: `python manage.py search_index --reindex --manager Projekt` (oder
äquivalent `--index projekte`). Ohne diesen Schritt liefert die Suche gegen den neuen
Index-Namen bis zum nächsten automatischen Reconcile-Lauf keine Treffer.

## Frontend-Änderungen

### `queries.ts`

- `GET_PROJEKTE` erhält `$page: Int!`:
  `projektList(page: $page, pageSize: 20, sortBy: [auftragsnummer], reverse: true) { items {...} pageInfo { totalCount } }`.
  `pageSize`/`sortBy`/`reverse` sind feste Literale, keine Variablen — es gibt keine UI, die
  sie ändert.
- `SEARCH_PROJEKTE`: einzige Änderung ist `index: "global"` → `index: "projekte"`. Sonst
  unverändert, inkl. `pageSize: 20` und `types: ["Projekt"]`.

### `ProjektListePage.tsx`

- **Sortierung:** siehe oben — komplett entfernt. Alle `<th>` werden statische Text-Header.
  Ungenutzte Icon-Imports (`ChevronsUpDown`, `ChevronUp`, `ChevronDown`) werden entfernt.
- **Infinite Scroll (nur `GET_PROJEKTE`):**
  - `useQuery(GET_PROJEKTE, { variables: { page: 1 }, fetchPolicy: "network-only" })` bleibt
    die Quelle der Wahrheit für Seite 1 (Initial-Load und Subscription-Reset). Ein lokaler
    `items`-State (`useState<Projekt[]>`) wird bei jeder neuen `data` aus diesem Hook auf
    `data.projektList.items` zurückgesetzt.
  - Nachladen läuft **nicht** über Apollos `fetchMore` (das würde ohne eigene
    Cache-Merge-Funktion die vorhandene Seite ersetzen statt anhängen), sondern über einen
    imperativen `client.query({ query: GET_PROJEKTE, variables: { page: next }, fetchPolicy: "network-only" })`
    via `useApolloClient()`. Das Ergebnis wird manuell an den lokalen `items`-State
    angehängt (`setItems(prev => [...prev, ...neue])`). Das umgeht Apollo-Cache-Merge-Konfiguration
    vollständig und bleibt damit der kleinste funktionierende Ansatz.
  - Ein `IntersectionObserver` (native Browser-API, keine neue Dependency) auf einem
    Sentinel-Element am Ende der Tabelle löst das Nachladen aus, sobald es sichtbar wird und
    `items.length < total` gilt. Ein `loadingMore`-Flag verhindert doppelte parallele
    Requests.
  - Bei einem Subscription-Event (`PROJEKT_LISTE_SUBSCRIPTION`) wird einfach auf Seite 1
    zurückgesetzt (`refetch({ page: 1 })`, Seiten-Zähler auf 1) — bereits nachgeladene
    Seiten werden verworfen. Kein Erhalt tieferer Scroll-Zustände.
- **Suche:** bleibt wie heute — feste `pageSize: 20`, kein Nachladen, kein Sentinel.
- **Summenanzeige:** wandert aus der `<h1>`-Kopfzeile neben das Suchfeld (mit Abstand, z. B.
  `ml-4`). Einheitlicher Text für beide Modi: `"{items.length} von {total} Projekten"` — die
  bisherige Sonderformulierung nur für den Listenmodus (`"{total} Projekte"` ohne Bezug zur
  geladenen Menge) entfällt, da jetzt auch die Liste potenziell nicht vollständig geladen
  ist.
- `PROJEKT_LISTE_SUBSCRIPTION` → `refetch()`: siehe Infinite-Scroll-Absatz oben.

## Out of Scope

- Sortierbarkeit irgendeiner Spalte — vollständig entfernt, kein Nachrüsten in dieser Spec.
- Pagination-UI (Zurück/Weiter, Seitenzahlen) — durch Infinite Scroll ersetzt.
- Nachladen/Infinite Scroll bei der Suche.
- Änderbare Seitengröße durch Nutzer:innen.
- Filter-UI (Status, Projektleiter-Dropdown) — weiterhin YAGNI.
- Wechsel des Initial-Loads von `GET_PROJEKTE` auf `search` — bewusst beibehalten wegen
  Live-Subscription.

## Testing

- Frontend (vitest): Sentinel-Intersection triggert Nachladen mit der korrekten nächsten
  `page`-Variable und hängt die Items an; ein Subscription-Event setzt Liste und Seitenzähler
  auf Seite 1 zurück und verwirft nachgeladene Seiten; Tabellenheader haben keine
  Klick-Handler mehr.
- Backend: kein neuer Testfall nötig, aber `tests/test_graphql_queries.py:119` muss den
  Index-String auf `"projekte"` mitziehen (siehe oben), sonst bricht der bestehende Test.
