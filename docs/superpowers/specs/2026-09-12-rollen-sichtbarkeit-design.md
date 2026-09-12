# Rollenabhängige Sichtbarkeit von Finanzdaten (Betrachter / Monteur)

**Datum:** 2026-09-12
**Status:** Entwurf, genehmigt zur Umsetzung

## Kontext

Forge kennt vier Django-Gruppen mit je einem registrierten Permission-String
(`apps/authentication/permission.py`): `Admin` → `isForgeAdmin`,
`Projektleiter` → `isProjektleiter`, `Betrachter` → `isBetrachter`,
`Monteur` → `isMonteur`.

Eine Prüfung des Ist-Zustands (GraphQL-Queries als Nutzer jeder Gruppe gegen
`/graphql/`) ergab drei Befunde:

1. **Monteur sieht keine Projektliste.** `Projekt.Permission.__read__` enthält
   `isMonteur` nicht; `projektList` liefert `items: []`. Das Spalten-Ausblenden
   im Frontend (`canViewFinanzen`) greift damit ins Leere.
2. **Die Calculation-Manager leaken Finanzdaten.** `IstWert` und
   `ProjektKennzahlen` haben nur `Permission = CalculationPermission` ohne
   eigenes `__read__`. Damit gilt der Settings-Default `READ: ["public"]`, und
   `CalculationPermission.get_read_permission_plan()` liefert bewusst "alle
   Zeilen, kein Instanz-Check" (Workaround für den `id__in`-Instanz-Check, der
   auf Calculation-Buckets fehlschlägt). Folge: `projekt(id).projektKennzahlenList`
   liefert einem Monteur `summeOfferteKosten`, obwohl `projekt.name` bereits
   `null` ist — und die Top-Level-Queries `projektKennzahlenList` / `istWertList`
   sind sogar **anonym** lesbar.
3. **Betrachter sieht exakt dasselbe wie Projektleiter**, weil
   `canViewFinanzen` nur "nicht Monteur" bedeutet und das Backend Betrachter
   überall zulässt.

Relevante GM-Mechanik (v0.79.3, gegen Quellcode verifiziert):

- Attribut-Regeln (`feld = {"read": [...]}`) greifen auch auf
  `@graph_ql_property`- und `*_list`-Feldern; ein verweigertes Feld kommt als
  `null` zurück, kein GraphQL-Fehler.
- Verschachtelte Listen (`projekt.kostenPositionenList`) werden mit dem
  Read-Plan des **Ziel-Managers** gefiltert; `deny_all` → `items: []`.
- Permissions werden nur an der GraphQL-Grenze geprüft. Python-interne
  Bucket-Zugriffe (`KostenPosition.filter(...)` in `ProjektKennzahlen`) sind
  nicht betroffen.
- `Manager.Permission(Manager, user)` (Klassen-Kontext) funktioniert für
  Gruppen-Regeln inklusive `__based_on__`-Delegation.

## Ziel

Sichtbarkeit pro Rolle — durchgesetzt im Backend, im Frontend nur abgebildet:

| Rolle | Projektliste | Detail: Header-Summen | Detail: Positionszeilen | Detail: Footer ab "Summe der Kosten" | Diagramm "Projektstatus auf einen Blick" |
|---|---|---|---|---|---|
| Admin / Projektleiter | alle Spalten | ja | ja | ja | ja |
| Betrachter | alle Spalten | ja | **nein** | ja | **nein** |
| Monteur | nur Auftragsnr., Name, Projektleiter, Status; **kein Klick ins Detail** | — (Route gesperrt) | — | — | — |
| anonym | nichts | — | — | — | — |

"Header-Summen" = Offerte exkl. MwSt., WV-Summe, Plan-WV-Summe in der
Projekt-Header-Card. "Footer" = die Zeilen Summe der Kosten, Gewinn / Verlust,
Differenz zu vorherigem, Bisher verr. Total, Abgrenzung, Vorrat mit allen
Spalten (Soll-Offerte, Soll-WV, Plan-WV, Ist, %).

## Nicht-Ziele

- Monteur-Stundenerfassung (Phase 2). Die heutige "Stunden-only"-Ansicht der
  Detailseite für Monteure wird entfernt, weil Monteure die Seite nicht mehr
  erreichen; sie kann in Phase 2 neu entworfen werden.
- Projektabhängige Sichtbarkeit (Objekt-Capability `projekt.capabilities.canViewKostenPositionen`).
  Heute gibt es keine projektabhängige Regel; globale Capabilities reichen.
- Änderung der Mutations-Permissions (`__create__/__update__/__delete__`) an
  irgendeinem Manager, inklusive der bestehenden Regel
  `auftragsnummer = {"update": ["isAdmin"]}`.
- `canCreateProjekt` und `canManageStundensaetze` bleiben unverändert.

## Design

### Backend — Permissions als einzige Quelle der Wahrheit

#### `Projekt` (`src/apps/projekt/models/projekt.py`)

```python
class Permission(AdditiveManagerPermission):
    __read__ = ["isForgeAdmin", "isProjektleiter", "isBetrachter", "isMonteur"]
    __create__ = ["isForgeAdmin", "isProjektleiter"]
    __update__ = ["isForgeAdmin", "isProjektleiter"]
    __delete__ = ["isForgeAdmin", "isProjektleiter"]
    graphql_capabilities: ClassVar[tuple[GraphQLPermissionCapability, ...]] = ()

    auftragsnummer = {"update": ["isAdmin"]}
    offerte_summe = {"read": ["isForgeAdmin", "isProjektleiter", "isBetrachter"]}
    wv_summe = {"read": ["isForgeAdmin", "isProjektleiter", "isBetrachter"]}
```

Wirkung: Monteur liest Projekte (Liste, Detail, Suche über
`search(index: "projekte")`), bekommt aber `offerteSumme` und `wvSumme` als
`null`. `AdditiveManagerPermission` AND-verknüpft Attribut- und Klassenregel;
für die drei Finanz-Rollen ändert sich nichts.

#### `KostenPosition` (`src/apps/projekt/models/kosten_position.py`)

```python
class Permission(AdditiveManagerPermission):
    __based_on__ = "projekt"
    __read__ = ["isForgeAdmin", "isProjektleiter"]
```

Wirkung: `kostenPositionenList.items` ist für Betrachter und Monteur leer.
Mutations-Regeln bleiben wie bisher (Default `isAuthenticated` AND
Projekt-Regel).

#### `IstWert` und `ProjektKennzahlen` (`src/apps/projekt/calculation_manager/`)

Beide ersetzen `Permission = CalculationPermission` durch eine innere
Subklasse mit explizitem `__read__`:

```python
# ist_wert.py
class Permission(CalculationPermission):
    __read__ = ["isForgeAdmin", "isProjektleiter"]

# projekt_kennzahlen.py
class Permission(CalculationPermission):
    __read__ = ["isForgeAdmin", "isProjektleiter", "isBetrachter"]
```

#### `CalculationPermission` (`src/apps/authentication/permission.py`)

Der Read-Plan wertet `__read__` statisch aus, bevor er den Instanz-Check
umgeht:

```python
class CalculationPermission(AdditiveManagerPermission):
    """Permission für CalculationInterface-Manager.

    GM's Instance-Check ruft queryset.filter(id__in=...) auf, was für
    CalculationBuckets fehlschlägt (kein 'id' im identification-dict).
    Deshalb wird __read__ hier statisch ausgewertet (Gruppen-Regeln brauchen
    keine Instanz): Unberechtigte bekommen deny_all, Berechtigte alle Zeilen
    ohne Instanz-Check.
    """

    def get_read_permission_plan(self) -> ReadPermissionPlan:
        if not self.check_operation_permission("read"):
            return ReadPermissionPlan(
                filters=[],
                requires_instance_check=False,
                decision="deny_all",
            )
        return ReadPermissionPlan(
            filters=[{"filter": {}, "exclude": {}}],
            requires_instance_check=False,
        )
```

`check_operation_permission("read")` ist öffentliche GM-API, enthält den
Superuser-Bypass und `__based_on__`. Ein Calculation-Manager, der nur
`Permission = CalculationPermission` ohne `__read__` setzt (heute:
`AufgabenStundensatz` in `apps/stunden`), behält den Settings-Default
`public` und damit das bisherige Verhalten — bewusst, weil dieser Manager
keine Finanzdaten liefert.

Wirkung: `projektKennzahlenList`, `istWertList` (Top-Level wie verschachtelt)
liefern Unberechtigten — inklusive anonym — `items: []`.

### Backend — Capabilities aus Permissions abgeleitet

`src/apps/authentication/graphql_capabilities.py` ersetzt die
hartcodierten Gruppen-Checks für Sichtbarkeit durch einen Helfer, der die
Permission-Klasse im Klassen-Kontext befragt:

```python
def _can_read(
    manager: type[GeneralManager],
    user: object,
    attribute: str | None = None,
) -> bool:
    permission = manager.Permission(manager, user)
    if attribute is None:
        return permission.check_operation_permission("read")
    return permission.check_permission("read", attribute)


def _can_view_finanzen(_instance: object, user: object) -> bool:
    return _can_read(Projekt, user, "offerte_summe")


def _can_view_kosten_positionen(_instance: object, user: object) -> bool:
    return _can_read(KostenPosition, user)
```

`CurrentUserCapabilities.graphql_capabilities` erhält zusätzlich
`object_capability("canViewKostenPositionen", _can_view_kosten_positionen)`.

- `canViewFinanzen` behält Name und Bedeutung (Admin, Projektleiter,
  Betrachter → True; Monteur, anonym → False), ist aber jetzt garantiert
  deckungsgleich mit dem, was `projekt.offerteSumme` liefert. Der
  `_user_or_none`-Sonderfall für AnonymousUser entfällt für diese Capability,
  weil `Projekt.__read__` eine Gruppe verlangt; für `canCreateProjekt` und
  `canManageStundensaetze` bleibt er bestehen.
- `canViewKostenPositionen`: Admin, Projektleiter → True; Betrachter,
  Monteur, anonym → False.

Import-Hinweis: `graphql_capabilities.py` importiert `Projekt` und
`KostenPosition` aus `apps.projekt.models`. Das Modul wird erst über den
`GRAPHQL_GLOBAL_CAPABILITIES_PROVIDER` geladen (nach `apps.populate()`),
also kein Zirkel- oder Registry-Problem. Sollte beim Umsetzen doch ein
`AppRegistryNotReady` auftreten, sind die Imports in die beiden Funktionen
zu verschieben (lokaler Import), nicht die Ableitung aufzugeben.

### GraphQL — resultierende Antworten

`me { capabilities { canCreateProjekt canManageStundensaetze canViewFinanzen canViewKostenPositionen } }`

`projektList` als Monteur: `items[].name` gefüllt, `offerteSumme: null`,
`wvSumme: null`, `projektKennzahlenList.items: []`.

`projekt(id)` als Betrachter: Header-Felder gefüllt, `projektKennzahlenList`
mit allen Kennzahlen, `kostenPositionenList.items: []`, `istWertList.items: []`.

`projektKennzahlenList` / `istWertList` anonym: `items: []`.

### Frontend

- `frontend/src/contexts/AuthContext.tsx`: `AuthCapabilities` um
  `canViewKostenPositionen: boolean` erweitern.
- `frontend/src/graphql/queries.ts`: `ME` fragt `canViewKostenPositionen` ab.
- `frontend/src/App.tsx`: Route `/projekte/:id` bekommt
  `requiredCapability="canViewFinanzen"`; `ProtectedRoute` leitet Monteure
  nach `/projekte` um (bestehendes Verhalten des Guards).
- `frontend/src/pages/ProjektListePage.tsx`: `onClick`-Navigation,
  `cursor-pointer`, Hover-Highlight und `ChevronRight` der Tabellenzeile nur
  bei `canViewFinanzen`. Finanzspalten (Offerte, WV + Zusätze, Abweichung zu
  Ist) hängen wie bisher an `canViewFinanzen`.
- `frontend/src/pages/ProjektDetailPage.tsx`:
  - Die `!showFinancials`-Zweige (Stunden-only-Ansicht: Überschrift
    "Stunden", Spalten "Ist"/"Ist %", `visibleReihen`-Filter auf `stunden`)
    werden entfernt; die Seite ist nach dem Route-Guard nur noch für Rollen
    mit `canViewFinanzen` erreichbar. Die Header-Summen werden ohne
    `showFinancials`-Bedingung gerendert.
  - Neu `showPositionen = user?.capabilities.canViewKostenPositionen ?? false`.
    Steuert: `visibleReihen` (bei `false` leer), die Legende
    "editierbar / berechnet / aus ERP" und `<ProjectVisualization>`.
    Tabellenkopf und Footer werden immer gerendert.
  - `canEditData` (aus `projekt.capabilities.canUpdate`) bleibt unverändert.

Das Frontend trifft keine Rollen-Entscheidung selbst; es liest nur die
beiden Capabilities.

### Tests

Backend (pytest, Coverage-Gate 100 %):

- Neu `src/apps/projekt/tests/test_permissions_graphql.py`: Matrix gegen
  `/graphql/` mit `Client.force_login` je Gruppe —
  - Monteur `projektList`: Item vorhanden, `name` gefüllt, `offerteSumme`
    und `wvSumme` `null`, `projektKennzahlenList.items == []`.
  - Betrachter `projekt(id)`: `offerteSumme` gefüllt,
    `projektKennzahlenList.items` mit `summeOfferteKosten`,
    `kostenPositionenList.items == []`, `istWertList.items == []`.
  - Projektleiter `projekt(id)`: alle drei Listen gefüllt.
  - anonym `projektKennzahlenList` und `istWertList`: `items == []`.
- `src/apps/authentication/tests/test_authentication.py`: Unit-Tests für
  `CalculationPermission.get_read_permission_plan()` —
  `IstWert.Permission(IstWert, monteur).get_read_permission_plan().decision == "deny_all"`,
  für Projektleiter `!= "deny_all"` mit `requires_instance_check is False`.
  Capability-Matrix (`me { capabilities }`) um `canViewKostenPositionen`
  ergänzen für Admin, Projektleiter, Betrachter, Monteur, anonym.

Frontend (vitest):

- `ProjektListePage.test.tsx`: mit `canViewFinanzen: false` fehlen die drei
  Finanzspalten, ein Klick auf eine Zeile navigiert nicht.
- `ProjektDetailPage.test.tsx`: mit `canViewKostenPositionen: false` keine
  Positionszeile (z. B. kein Text "Apparate"), aber "Summe der Kosten" und
  "Offerte exkl. MwSt." vorhanden und kein "Projektstatus auf einen Blick";
  mit `true` alles vorhanden.

### Doku

- `CONTEXT.md`, Abschnitt "Stakeholder & Rollen": Betrachter → "Lesezugriff
  auf Projekte und Kennzahlen; keine einzelnen Kostenpositionen, kein
  Diagramm; keine Bearbeitung". Monteur → "Projektliste ohne Finanzspalten;
  kein Zugriff auf Projektdetails; Stundenerfassung in Phase 2".
- `.claude/skills/general-manager/references/reference.md` §5: das
  `CalculationPermission`-Snippet auf die neue Fassung heben und den Satz
  ergänzen, dass jeder Calculation-Manager mit sensiblen Daten ein
  explizites `__read__` braucht.

## Offene Risiken

- `check_operation_permission("read")` im Klassen-Kontext ist für
  Gruppen-Regeln verifiziert; für instanzabhängige Regeln (z. B.
  `relatedUserField`) würde es False liefern. Calculation-Manager in Forge
  nutzen nur Gruppen-Regeln — falls das einmal nicht mehr gilt, muss
  `CalculationPermission` erweitert werden.
- Das Entfernen der Stunden-only-Ansicht ist ein bewusster Bruch mit der
  bisherigen Monteur-Vorbereitung; Phase 2 entwirft die Stundenerfassung neu.
