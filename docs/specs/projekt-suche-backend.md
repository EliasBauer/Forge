# Spec: Projekt-Suche über das Backend (GM/Meilisearch)

## Ziel

Die Suche auf der Projektliste ([ProjektListePage.tsx](../../frontend/src/pages/ProjektListePage.tsx)) filtert
heute rein clientseitig über die bereits geladenen (max. 100) Projekte. Sie wird auf die
Volltext-Suche des GeneralManager-Frameworks (§11 der GM-Skill-Referenz) umgestellt, produktiv
über Meilisearch. Meilisearch läuft bereits als Service in
[docker-compose.yml](../../docker/docker-compose.yml), ist aber bisher nicht angebunden.

## Ist-Zustand

- `ProjektListePage.tsx` lädt via `GET_PROJEKTE` (`projektList(pageSize: 100)`) alle Projekte und
  filtert per `Array.filter` auf `name`, `auftragsnummer`, `projektleiter` (Substring, lowercase).
- Kein `SearchConfig` auf `Projekt` ([src/apps/projekt/models/projekt.py](../../src/apps/projekt/models/projekt.py)).
- Kein Such-Backend in `GENERAL_MANAGER`-Settings konfiguriert.
- `meilisearch`-Python-Client ist keine Dependency.
- Devcontainer (`.devcontainer/devcontainer.json`) setzt kein `.env`, nur `FORGE_ENV=dev` — läuft
  komplett ohne externe Services (SQLite statt Postgres, LocMem statt Redis).

## Backend-Auswahl: dev vs. produktiv

Gleiches Muster wie `CACHES`/`CHANNEL_LAYERS` in [settings.py:97-124](../../src/forge/settings.py):
Entscheidung anhand Vorhandensein der Env-Var, nicht anhand `FORGE_ENV`.

```python
MEILISEARCH_URL = os.environ.get("MEILISEARCH_URL", "")

GENERAL_MANAGER = {
    "AUTOCREATE_GRAPHQL": True,
    "GRAPHQL_URL": "graphql/",
    "DEFAULT_PERMISSIONS": {...},  # unverändert
    "SEARCH_AUTO_REINDEX": True,
    "SEARCH_RECONCILE_ENABLED": True,
    "SEARCH_RECONCILE_INTERVAL_SECONDS": 30,
    "SEARCH_BACKEND": {
        "class": "general_manager.search.backends.meilisearch.MeilisearchBackend",
        "options": {
            "url": MEILISEARCH_URL,
            "api_key": os.environ.get("MEILISEARCH_MASTER_KEY") or None,
        },
    } if MEILISEARCH_URL else None,
}
```

- **Dev (Devcontainer):** `MEILISEARCH_URL` ist nicht gesetzt → `SEARCH_BACKEND` ist `None` → GM
  fällt automatisch auf `DevSearchBackend` zurück (bestätigt in
  `general_manager/search/backend_registry.py:169-177`). `SEARCH_AUTO_REINDEX: True` sorgt dafür,
  dass der In-Memory-Index beim ersten Suchaufruf pro Prozess lazy aus der DB befüllt wird — kein
  manueller Reindex nötig.
- **Produktiv (Docker Compose):** `MEILISEARCH_URL=http://meilisearch:7700` ist gesetzt (bereits in
  `.env.example`) → echtes Meilisearch-Backend.

Bewusst ausgelassen: `SEARCH_ASYNC` (Celery-basierte async Indexierung) — bei der aktuellen
Projekt-Datenmenge lohnt sich der zusätzliche Async-Pfad nicht, inline reicht. Celery-Worker
existiert bereits, Nachrüsten ist ein reines Settings-Flag, falls es mal eng wird.

## Dependency

`uv add meilisearch` — der Python-Client wird von `MeilisearchBackend` nur bei gesetzter
`MEILISEARCH_URL` überhaupt importiert.

## SearchConfig auf `Projekt`

In [src/apps/projekt/models/projekt.py](../../src/apps/projekt/models/projekt.py), indexiert
dieselben Felder, die heute clientseitig gefiltert werden:

```python
from general_manager import FieldConfig, IndexConfig

class Projekt(GeneralManager):
    ...
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

`projektleiter` ist ein rohes Django-`ForeignKey` auf `auth.User` (kein GM-Manager); die
Feldauflösung im Indexer traversiert Attribute generisch per `getattr`, `__username` funktioniert
also genau wie jeder Django-`__`-Lookup. `auth.User` hat kein `__str__`-Override in Forge, die
GraphQL-Anzeige von `projektleiter` ist bereits `str(User)` = `username` — dieselbe Quelle wird
indexiert.

Kein `filters`/`sorts` in der `IndexConfig`: Es gibt aktuell keine UI-Filtersteuerung, und die
Tabelle sortiert ohnehin clientseitig über die zurückgegebenen Treffer (`sortProjekte`). YAGNI,
bei Bedarf nachrüstbar.

## Index-Pflege

- **Laufende Änderungen:** automatisch — Schreiboperationen auf `Projekt` markieren den Index
  „dirty", kein zusätzlicher Code nötig.
- **Reconciliation:** GM registriert den periodischen Sweep selbst in Celery Beat
  (`general_manager.apps.GeneralManagerConfig.ready()` ruft
  `configure_search_reconcile_beat_schedule_from_settings()` auf, Task
  `general_manager.search.tasks.reconcile_search_indexes_task`). Kein manueller
  `CELERY_BEAT_SCHEDULE`-Eintrag nötig — nur zwei Settings in `GENERAL_MANAGER`:
  ```python
  GENERAL_MANAGER = {
      ...,
      "SEARCH_RECONCILE_ENABLED": True,
      "SEARCH_RECONCILE_INTERVAL_SECONDS": 30,
  }
  ```
  (Celery-Beat-Infra inkl. `django_celery_beat.schedulers:DatabaseScheduler` läuft bereits.)
- **Einmaliger Erstaufbau (Deploy):** `python manage.py search_index --reindex` für die
  produktiv bereits existierenden Projekt-Datensätze, einmalig als Deploy-Schritt.
- Migration `0011_search_index_state_dirty_generation` ist Teil des installierten
  `general_manager`-Pakets und wird über den ohnehin vorhandenen `manage.py migrate`-Schritt
  mit ausgerollt.

## Frontend

In [ProjektListePage.tsx](../../frontend/src/pages/ProjektListePage.tsx):

- Neue GraphQL-Query gegen den GM-`search`-Root-Query:
  ```graphql
  query SearchProjekte($query: String!) {
    search(query: $query, index: "global", types: ["Projekt"], pageSize: 20) {
      results {
        ... on ProjektType {
          id
          auftragsnummer
          name
          offerteSumme { value unit }
          wvSumme { value unit }
          auftragFertig
          projektleiter
          projektKennzahlenList { items { summeWvPlus { value unit } summeIstKosten { value unit } } }
        }
      }
      total
    }
  }
  ```
  (GraphQL-Typname `ProjektType` verifiziert gegen `general_manager/api/graphql.py:791`:
  `graphene_type_name = f"{generalManagerClass.__name__}Type"` — GM hängt an jeden Manager-Namen
  im autogenerierten Schema `Type` an.)
- Eingabe wird debounced (~300ms).
- Leeres Suchfeld → unverändertes Verhalten: `GET_PROJEKTE` mit Live-Subscription
  (`PROJEKT_LISTE_SUBSCRIPTION`), volle Liste.
- Nicht-leeres Suchfeld → `SearchProjekte`-Ergebnisse ersetzen die Datenquelle der Tabelle; gleiche
  Spalten, gleiche clientseitige Sortierung (`sortProjekte`) wie bisher. Kein Tabellen-Rewrite.
- Permissions: GM wendet die `Projekt.Permission.__read__`-Regeln automatisch auf Suchtreffer an,
  kein zusätzlicher Code nötig.

## Testing

- Ein Backend-Test gegen `DevSearchBackend` (kein externer Service nötig): Projekt anlegen, prüfen,
  dass es über die konfigurierten Felder (`name`, `auftragsnummer`, `projektleiter__username`)
  gefunden wird.
- Bestehende Frontend-Tests (vitest) um den Such-Query-Switch ergänzen, falls dort bereits
  Konventionen für Query-Mocking existieren (bei Implementierung gegen `frontend/src` prüfen).

## Out of Scope

- Filter-UI (Status, Projektleiter-Dropdown) — kein `filters`-Config, YAGNI.
- Suche über weitere Manager-Typen (aktuell nur `Projekt`, `types: ["Projekt"]` fest verdrahtet).
- `SEARCH_ASYNC` / Celery-Indexierung.
- Server-seitige Pagination der Suchergebnisse über `pageSize: 20` hinaus.
