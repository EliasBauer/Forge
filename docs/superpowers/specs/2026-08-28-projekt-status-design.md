# ProjektStatus: Ablösung von `auftrag_fertig`

**Datum:** 2026-08-28
**Status:** Entwurf, genehmigt zur Umsetzung

## Kontext

`Projekt` hat aktuell ein Boolean-Feld `auftrag_fertig` (fertig/nicht fertig). Das
reicht nicht mehr: es soll einen dritten Zwischenzustand geben. Statt eines
dritten Booleans oder einer Enum-Choice führen wir ein eigenes
`ProjektStatus`-Lookup-Modell ein, analog zum bereits vorhandenen
`Kostenart`-Muster in diesem Projekt (`src/apps/projekt/models/kostenart.py`).

## Ziel

- `ProjektStatus` als `ReadOnlyInterface`-GeneralManager mit einzigem Feld
  `name`, drei feste Einträge: `Offen`, `In Arbeit`, `Fertig`.
- `Projekt.auftrag_fertig` (Boolean) wird entfernt, ersetzt durch
  `Projekt.projekt_status` (FK auf `ProjektStatus`).
- Jede Stelle im Frontend, die bisher `auftragFertig` gelesen oder geschrieben
  hat, arbeitet stattdessen mit `projektStatus.name` bzw. der `projektStatus`-ID.
- Migration bestehender Daten: `True` → `Fertig`, `False` → `In Arbeit`.
  Default für neu angelegte Projekte: `Offen`.

## Nicht-Ziele

- Keine eigene "Stammdaten"-Seite/Reiter im Frontend zur Anzeige oder
  Bearbeitung von `ProjektStatus`. Die drei Einträge sind fest im Code
  definiert (`_data`); neue Einträge kommen künftig per Code-Änderung, nicht
  per UI (Konsequenz aus `ReadOnlyInterface`: Schreibversuche zur Laufzeit
  werfen eine Exception, siehe `general-manager`-Skill, Abschnitt "ReadOnly").
- Keine Sortier-/Filterfunktion nach Status in der Projektliste (existiert für
  `auftrag_fertig` heute auch nicht).

## Design

### Backend

**Neues Modell** `src/apps/projekt/models/projekt_status.py`:

```python
class ProjektStatus(GeneralManager):
    id: int
    name: str

    _data = [
        {"name": "Offen"},
        {"name": "In Arbeit"},
        {"name": "Fertig"},
    ]

    class Interface(ReadOnlyInterface):
        name = models.CharField(max_length=50, unique=True)

    class Permission(AdditiveManagerPermission):
        pass
```

In `src/apps/projekt/models/__init__.py` registrieren (analog `Kostenart`).

**`Projekt`-Änderungen** (`src/apps/projekt/models/projekt.py`):

- `auftrag_fertig: bool` → entfällt.
- Neu: `projekt_status: ProjektStatus`.
- Interface-Feld: `models.ForeignKey("projekt.ProjektStatus", on_delete=models.PROTECT, related_name="projekte")`
  — analog zu `KostenPosition.art` (FK auf eine andere GeneralManager-Klasse).
  Kein manuelles `_id`-Mapping in `create()`/`update()` nötig, GM löst das für
  FK-auf-GeneralManager-Felder selbst auf (im Gegensatz zu `projektleiter`,
  das auf das rohe Django-Model `auth.User` zeigt).
- `Projekt.create()`: wenn `projekt_status` nicht in `kwargs` übergeben wird,
  Default auf `ProjektStatus.filter(name="Offen").first()` setzen (gleiches
  Override-Pattern wie bereits für `projektleiter` vorhanden). Das entkoppelt
  den Default von der (nicht garantiert stabilen) Auto-PK der ReadOnly-Zeilen.

**Migration:**

1. Schema-Migration (`makemigrations`): legt `ProjektStatus`-Tabelle an, fügt
   `projekt_status` als FK auf `Projekt` hinzu (zunächst nullable, damit die
   folgende Datenmigration befüllen kann).
2. Datenmigration: pro `Projekt`-Zeile `projekt_status` setzen —
   `True → "Fertig"`, `False → "In Arbeit"`. Voraussetzung: die
   `ReadOnlyInterface`-Sync-Logik von `ProjektStatus` muss vor dieser
   Migration gelaufen sein (passiert beim App-Start / `apps.ready()`, also vor
   der Ausführung von `manage.py migrate` im selben Prozess — wie schon für
   `Kostenart` in diesem Projekt vorausgesetzt). Falls das nicht zuverlässig
   greift, in der Migration selbst per `RunPython` die drei `ProjektStatus`-
   Zeilen defensiv anlegen (`get_or_create`), bevor gemappt wird.
3. Weitere Migration: `projekt_status` auf `null=False` setzen,
   `auftrag_fertig` droppen.

**Admin** (`src/apps/projekt/admin.py`): `auftrag_fertig` in `list_display`
und `list_filter` durch `projekt_status` ersetzen.

### GraphQL

- `projektStatus` erscheint automatisch als Sub-Objekt
  (`projektStatus { name }`), da beide Seiten GeneralManager sind (siehe
  `KostenPosition.art` → `art { schluessel }`).
- `createProjekt` bleibt unverändert (kein `projektStatus`-Parameter) — das
  Backend setzt den Default „Offen" serverseitig (`Projekt.create()`).
  `updateProjekt` nimmt optional `$projektStatus: ID` entgegen.
- Neue Query `GET_PROJEKT_STATUS_IDS` (`frontend/src/graphql/queries.ts`,
  analog `GET_KOSTENART_IDS`), liefert `{ projektStatusList: { items: { id
  name } } }` — wird ausschließlich intern vom Bearbeiten-Formular auf der
  Detailseite genutzt, um die drei Auswahloptionen zu laden. Keine
  eigene Seite/Route dafür.

### Frontend

Alle Fundstellen von `auftrag_fertig`/`auftragFertig` umstellen:

- `frontend/src/graphql/queries.ts`, `mutations.ts`, `subscriptions.ts`:
  `auftragFertig` → `projektStatus { id name }` (in Queries),
  `$projektStatus: ID` (in Mutations).
- `ProjektListePage.tsx`:
  - Typ `auftragFertig: boolean` → `projektStatus: { id: string; name: string }`.
  - `StatusBadge`: statt zweier Zustände (Aktiv/Archiviert) drei farbige
    Varianten nach `projektStatus.name`: **Offen** = blau, **In Arbeit** =
    grün, **Fertig** = grau.
- `ProjektDetailPage.tsx`:
  - Der bisherige sofort-wirkende "Archivieren"/"Reaktivieren"-Button entfällt
    ersatzlos.
  - `projekt_status` wird ein `<select>`-Feld im bestehenden
    "Bearbeiten"-Formular (`headerForm`/`editingHeader`), Optionen aus
    `PROJEKT_STATUS_LIST`. Übernommen wird der Wert erst mit dem allgemeinen
    "Speichern"-Klick (`saveHeader()`), wie Name/Summen/Projektleiter — keine
    separate Sofort-Mutation mehr.
  - Der Status-Hinweis im Header (bisher: grauer "Fertig"-Badge nur wenn
    `auftrag_fertig === true`) zeigt außerhalb des Edit-Modus den aktuellen
    `projektStatus.name` an (für alle drei Zustände, nicht nur "Fertig").
- `ProjektNeuPage.tsx`: keine Änderung — neue Projekte bekommen den Default
  "Offen" serverseitig, kein Formularfeld nötig.

### Tests

- `src/apps/projekt/tests/test_projekt.py`: `test_auftrag_fertig_default_ist_false`
  → `test_projekt_status_default_ist_offen`; Feldnamen-Assertion anpassen.
- Neue `src/apps/projekt/tests/test_projekt_status.py` analog
  `test_kostenart.py` (drei Einträge vorhanden, `name`-Unique-Constraint).
- `tests/test_graphql_queries.py`: `auftragFertig` → `projektStatus { name }`
  in den Query-Strings.
- `frontend/src/pages/ProjektListePage.test.tsx`: Mock-Daten und Assertions
  auf `projektStatus` umstellen.

## Offene Risiken

- Die Reihenfolge-/Timing-Annahme bei der Datenmigration (ReadOnly-Sync läuft
  vor der Migration) ist in diesem Projekt für `Kostenart` bereits implizit
  vorausgesetzt, aber nicht explizit getestet. Falls die Migration in der
  Praxis leere `ProjektStatus`-Tabelle vorfindet, greift der defensive
  `get_or_create`-Fallback in der Migration selbst (siehe oben).
