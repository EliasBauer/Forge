# GeneralManager – Patterns & Konventionen für Forge

> Zweck: Lokale Referenz für Claude Code und Entwickler. Beschreibt die Patterns,
> Konventionen und Gotchas des GeneralManager-Frameworks, wie wir sie in Forge verwenden.
>
> Upstream-Doku: https://timkleindick.github.io/general_manager/
> Repo: https://github.com/TimKleindick/general_manager
> Aktuelle Version: 0.45.0

---

## Inhaltsverzeichnis

1. [Architektur-Überblick](#1-architektur-überblick)
2. [Manager-Klassen definieren](#2-manager-klassen-definieren)
3. [CRUD-Operationen](#3-crud-operationen)
4. [Buckets (Collections)](#4-buckets-collections)
5. [Permissions (ABAC)](#5-permissions-abac)
6. [Validators / Rules](#6-validators--rules)
7. [Factories & Seeding](#7-factories--seeding)
8. [MeasurementField](#8-measurementfield)
9. [GraphQL-Integration](#9-graphql-integration)
10. [GraphQL Subscriptions](#10-graphql-subscriptions)
11. [Search](#11-search)
12. [Caching](#12-caching)
13. [History / Audit Trail](#13-history--audit-trail)
14. [Observability / Logging](#14-observability--logging)
15. [RequestInterface](#15-requestinterface)
16. [Workflow-Automation](#16-workflow-automation)
17. [INSTALLED_APPS-Reihenfolge](#17-installed_apps-reihenfolge)
18. [CSRF & Frontend-Anbindung](#18-csrf--frontend-anbindung)
19. [Häufige Gotchas](#19-häufige-gotchas)
20. [Weiterführende Upstream-Doku](#20-weiterführende-upstream-doku)

---

## 1) Architektur-Überblick

GeneralManager erweitert Django um eine deklarative Schicht aus vier Kernkomponenten:

- **Manager** – Leichtgewichtiger Wrapper um ein Interface. Exponiert Attribute als
  Python-Type-Hints, proxied CRUD-Operationen ans Interface. Jede Instanz hält ein
  `identification`-Dict, das den zugrundeliegenden Record eindeutig identifiziert.

- **Interface** – Implementiert die Persistenz-Strategie (capability-first intern):
  - `DatabaseInterface` – eigene Tabelle (Standard)
  - `ExistingModelInterface` – bestehendes Django-Model
  - `ReadOnlyInterface` – statische Daten (aus `_data`-Liste)
  - `CalculationInterface` – berechnete Werte ohne DB
  - `RequestInterface` – Daten von externen HTTP-Services

- **Bucket** – Typisierte Collection von Managern (ähnlich Queryset).
  Unterstützt `filter()`, `exclude()`, `sort()`, `group_by()`, Union (`|`). Lazy.
  Konkrete Subtypen: `DatabaseBucket`, `RequestBucket`, `CalculationBucket`, `GroupBucket`.

- **Dependency Tracker** – Jede Datenänderung emittiert Signale. Der Tracker mappt
  Attributzugriffe auf Cache-Keys und invalidiert abhängige Einträge automatisch.

### Lifecycle

1. Django-Start: Manager-Klassen importiert, Interfaces registrieren Models.
2. `GeneralmanagerConfig.ready()` initialisiert GM-Klassen, erstellt GraphQL-Schema
   wenn `AUTOCREATE_GRAPHQL = True`.
3. Requests instanziieren Manager/Buckets.
4. Mutations emittieren Dependency-Signale → Cache wird invalidiert.

---

## 2) Manager-Klassen definieren

### Grundstruktur

Typ-Annotationen gehören **auf die GM-Klasse** (echte Python-Typen, kein `Any`).
Im `Interface(DatabaseInterface)` stehen **nur** die Model-Field-Definitionen.

```python
from django.db import models
from general_manager import DatabaseInterface, GeneralManager, AdditiveManagerPermission


class Projekt(GeneralManager):
    auftragsnummer: str
    bezeichnung: str
    kunde: str | None

    class Interface(DatabaseInterface):
        auftragsnummer = models.CharField(max_length=20, unique=True)
        bezeichnung = models.CharField(max_length=200)
        kunde = models.CharField(max_length=200, null=True, blank=True)

    class Permission(AdditiveManagerPermission):
        pass
```

### Computed Properties (GraphQL-exponiert)

```python
from general_manager.api.property import graph_ql_property


class Projekt(GeneralManager):
    startdatum: date
    enddatum: date | None

    @graph_ql_property
    def dauer_tage(self) -> int | None:
        if not self.startdatum or not self.enddatum:
            return None
        return (self.enddatum - self.startdatum).days

    # sortable/filterable: Feld erscheint in GraphQL-Filter- und Sort-Argumenten
    @graph_ql_property(sortable=True, filterable=True)
    def gesamtkosten(self) -> Measurement | None:
        ...
```

**Cache-Modus** (Default ist `run` — historisch: der frühere `auto`-Modus wurde in
0.42.0 entfernt):

| Decorator                                | Verhalten                                                                    |
| ---------------------------------------- | ---------------------------------------------------------------------------- |
| `@graph_ql_property`                     | `cache="run"` (Default) — Ergebnis wird innerhalb eines GraphQL-Runs gecacht |
| `@graph_ql_property(cache="dependency")` | Persistent gecacht, invalidiert wenn abhängige Manager sich ändern           |
| `@graph_ql_property(cache="none")`       | Kein Caching, bei sehr einfachen/billigen Properties                         |

Gültige Cache-Modi für `@graph_ql_property`: `run | dependency | none`. (Den vierten
`cached`-Scope `timeout` gibt es nur beim eigenständigen `@cached`-Decorator, nicht
für GraphQL-Properties — siehe Abschnitt 12.)

Für CalculationInterface-Properties mit DB-Zugriffen ist `cache="run"` (Default)
ausreichend — für teure Berechnungen, die Request-übergreifend gecacht werden sollen,
`cache="dependency"` verwenden.

### Beziehungen zwischen Managern

```python
class Position(GeneralManager):
    projekt: Projekt
    beschreibung: str

    class Interface(DatabaseInterface):
        projekt = models.ForeignKey(
            "projekt.Projekt", on_delete=models.CASCADE, related_name="positionen"
        )
        beschreibung = models.CharField(max_length=500)
```

`Projekt` bekommt damit automatisch ein `position_list`-Attribut (Bucket).

> **Achtung GraphQL:** ForeignKeys werden als **String** (`str()` des Objekts)
> serialisiert, nicht als verschachteltes Objekt.

### Interface-Optionen

```python
class Interface(DatabaseInterface):
    class Meta:
        use_soft_delete = True     # is_active-Flag; .objects filtert, .all_objects nicht
        database = "secondary"     # DB-Alias

    def full_clean(self, *args, **kwargs):
        # Validierung vor dem Speichern (ACHTUNG: super() geht nicht – siehe Gotchas)
        _call_parent_full_clean(self, *args, **kwargs)
```

### ExistingModelInterface

Bestehendes Django-Model wrappen – keine neuen Tabellen, aber voller GM-Layer:

```python
from existing_app.models import UserModel

class UserManager(GeneralManager):
    email: str
    is_active: bool

    class Interface(ExistingModelInterface):
        model = UserModel  # oder settings.AUTH_USER_MODEL als String
```

- `create()`, `update()` (in-place, gleiche Instanz), `delete()` (invalidiert Instanz)
- History-Tracking via `django-simple-history` (`changed_by_id`, `history_comment`)
- Soft-delete schaltet `is_active` automatisch wenn das Flag vorhanden ist
- Datei-Organisation: Original in `models.py`, Wrapper in `managers.py` (verhindert Import-Zyklen)

### ReadOnlyInterface

Statische Datensätze, z.B. Lookup-Tabellen:

```python
class Kostenart(GeneralManager):
    schluessel: str
    name: str
    ist_ertragsblock: bool
    konto_nummer: int | None

    # _data gehört auf die Manager-Klasse, NICHT auf Interface
    _data = [
        {"schluessel": "regie",  "name": "Regie",  "ist_ertragsblock": True,  "konto_nummer": None},
        {"schluessel": "arbeit", "name": "Arbeit", "ist_ertragsblock": False, "konto_nummer": 4001},
    ]

    class Interface(ReadOnlyInterface):
        schluessel       = models.CharField(max_length=50, unique=True)
        name             = models.CharField(max_length=200)
        ist_ertragsblock = models.BooleanField(default=False)
        konto_nummer     = models.IntegerField(null=True, blank=True)

    class Permission(AdditiveManagerPermission):
        pass
```

`ReadOnlyInterface` synchronisiert `_data` beim Start (create/update/soft-delete);
intern liest die Sync-Logik das Attribut via `getattr(<Manager-Klasse>, "_data")`.
Write-Versuche zur Laufzeit werfen Exceptions.

### CalculationInterface

Berechnete Werte ohne Persistenz. Inputs via `Input`-Klasse:

```python
from general_manager import CalculationInterface, GeneralManager, Input


class IstWert(GeneralManager):
    projekt: Projekt
    kostenart: Kostenart

    class Interface(CalculationInterface):
        # Input definiert erlaubte Eingabewerte (keine DB-Felder)
        projekt   = Input(Projekt,   possible_values=lambda: Projekt.all())
        kostenart = Input(Kostenart, possible_values=lambda: Kostenart.all())

    Permission = CalculationPermission  # siehe Abschnitt 5

    @graph_ql_property
    def gesamtkosten(self) -> Measurement | None:
        ...
```

**Input – Konstruktor und Helfer.** Der erste Positionsparameter heißt `type`
(`Input(date)` oder `Input(type=date)`). `required` ist keyword-only.

```python
# Optionales Input
datum = Input(date, required=False)

# Datum-Domains (strukturiert) — ACHTUNG: alle Parameter sind keyword-only,
# und ALLE drei Helfer nehmen `start`/`end` als date-Werte (keine Jahres-Shortcuts).
datum = Input.date_range(start=date(2026, 1, 1), end=date(2026, 12, 31))

# Monatliche Stützstellen über einen start/end-Bereich (anchor="month_end" als Default)
monat = Input.monthly_date(start=date(2026, 1, 1), end=date(2026, 12, 31))

# Jährliche Stützstellen über einen start/end-Bereich (anchor="year_end" als Default)
jahr  = Input.yearly_date(start=date(2020, 1, 1), end=date(2030, 12, 31))

# Abhängigkeit zwischen Inputs deklarieren
quartal = Input(str, depends_on=["jahr"])
```

> **Falsch (häufiger Irrtum):** `Input.monthly_date(year=2026)` oder
> `Input.yearly_date(start_year=2020, end_year=2030)` existieren **nicht** und werfen
> `TypeError`. Alle Domain-Helfer arbeiten ausschließlich mit `start`/`end`
> (`date`-Objekte oder Callables, die ein `date` liefern), plus optional `anchor`/`step`.

`possible_values` steuert, welche Kombinationen im GraphQL-Schema aufgelistet werden.

> **Empfehlung: `possible_values` sollte einen Bucket liefern, keine reine Python-Liste.**
>
> Technisch akzeptiert `Input` zwar auch ein Iterable, aber ein Bucket ist das, was du
> in der Praxis willst: Beim Auflisten/Filtern im GraphQL-Schema wird die Auswahl per
> `.filter(id=...)` eingegrenzt. Eine reine Liste hat kein `.filter()`, daher kann sie
> nicht eingegrenzt werden — die Query liefert dann effektiv alle Werte.
>
> ```python
> # SCHLECHT – list() kann nicht gefiltert werden, Query liefert alle Projekte
> projekt = Input(Projekt, possible_values=lambda: list(Projekt.all()))
>
> # GUT – Filter wird als .filter(id=1) auf den Bucket angewendet
> projekt = Input(Projekt, possible_values=lambda: Projekt.all())
> ```

### Many-to-Many

```python
Projekt.create(
    creator_id=user.id,
    stakeholder_id_list=[1, 2, 3],  # _id_list-Konvention
)
projekt.update(creator_id=user.id, stakeholder_id_list=[2, 4, 5])
```

---

## 3) CRUD-Operationen

Alle Methoden akzeptieren `creator_id` und optional `history_comment` (beide optional;
ohne `creator_id` wird kein History-User gesetzt):

```python
# Erstellen
projekt = Projekt.create(
    creator_id=request.user.id,
    history_comment="Neues Projekt angelegt",
    auftragsnummer="2026-001",
    bezeichnung="Lüftung Rohbau",
)

# Aktualisieren (in-place, gibt dieselbe Instanz zurück)
projekt.update(
    creator_id=request.user.id,
    bezeichnung="Lüftung Rohbau – Phase 2",
)
# projekt.bezeichnung ist danach sofort aktuell

# Löschen (invalidiert die Instanz für weitere Attributzugriffe)
projekt.delete(
    creator_id=request.user.id,
    history_comment="Projekt storniert",
)
```

### Lesen: `get`-Shortcut (ab 0.44.0)

`Manager.get(**kwargs)` ist ein Convenience-Wrapper für `filter(**kwargs).get()` und
liefert genau eine Instanz (mit dem Einzeltreffer-Exception-Verhalten des Buckets):

```python
projekt = Projekt.get(id=42)
projekt = Projekt.get(auftragsnummer="2026-001")
```

Für Mengen weiterhin `Projekt.filter(...)` / `Projekt.all()` (Abschnitt 4).

### Soft Deletes

```python
class Meta:
    use_soft_delete = True

# .objects      → nur aktive Records (is_active=True)
# .all_objects  → alle (inkl. is_active=False)
# Projekt.filter(include_inactive=True)  → inkl. deaktivierte
```

---

## 4) Buckets (Collections)

### Erstellen

```python
alle    = Projekt.all()
aktive  = Projekt.filter(auftrag_fertig=False)
exkl    = Projekt.exclude(status="archiviert")
kombi   = aktive | exkl   # Union (OR)
```

### Filtern & Ausschliessen

Unterstützt Django ORM-Lookups: `__exact`, `__icontains`, `__gte`, `__lte`,
`__in`, `__range`, `__isnull`, `__startswith`, …

```python
bucket.filter(
    name__icontains="test",
    startdatum__gte=date(2026, 1, 1),
    status__in=["active", "pending"],
)
bucket.exclude(deleted=True)
# Chaining
bucket.filter(...).filter(...).exclude(...)
```

Historische Abfragen (Point-in-time):

```python
stand = Projekt.filter(search_date=datetime(2026, 1, 1))
```

### Sortieren

```python
bucket.sort("name")              # aufsteigend
bucket.sort("-startdatum")       # absteigend
bucket.sort(("-datum", "name"))  # mehrere Felder
```

### Gruppieren

```python
grouped = Projekt.filter().group_by("kunde", "status")

for group_manager in grouped:
    print(group_manager.group_key)   # {"kunde": "X", "status": "Y"}
    for projekt in group_manager:
        print(projekt.name)
```

### Zugriff

```python
first  = bucket.first()         # erstes oder None
last   = bucket.last()          # letztes oder None
item   = bucket.get(id=42)      # genau einer; wirft wenn keiner/mehrere
item   = bucket[0]              # Index
items  = bucket[1:10]           # Slice → Bucket
count  = bucket.count()         # lazy DB-count
exists = 42 in bucket
```

> `Manager.get(**kwargs)` (Abschnitt 3) ist der Shortcut für `Manager.filter(**kwargs).get()`.

### Bucket-Dependency-Semantik (wichtig für Caching)

Dependency-Tracking erfolgt **lazy**: erst beim tatsächlichen Auswerten
(Iteration, `count()`, `first()`, `get()`, `bucket[0]`, `len()`, `in`),
nicht beim Konstruieren des Buckets. Verkettete `filter()`-Aufrufe werden
zu einem einzigen Dependency-Eintrag zusammengeführt.

---

## 5) Permissions (ABAC)

### Grundkonfiguration

```python
from general_manager import AdditiveManagerPermission


class Projekt(GeneralManager):
    class Permission(AdditiveManagerPermission):
        __read__   = ["public"]
        __create__ = ["isAdmin"]
        __update__ = ["isAuthenticated"]
        __delete__ = ["isAdmin"]
```

**`AdditiveManagerPermission`** vs **`OverrideManagerPermission`**:

- `AdditiveManagerPermission`: Attribut-spezifische Regel wird **zusätzlich** zur Klassen-Regel geprüft (AND).
- `OverrideManagerPermission`: Attribut-spezifische Regel **ersetzt** die Klassen-Regel für dieses Feld.
- `ManagerBasedPermission` ist ein veralteter, abwärtskompatibler Alias (Subklasse) von `AdditiveManagerPermission` — nicht mehr verwenden.

### Defaults aus Settings

Nicht explizit definierte `__read__` / `__create__` / `__update__` / `__delete__`
werden aus `GENERAL_MANAGER["DEFAULT_PERMISSIONS"]` befüllt:

```python
# Forge settings.py — alle Aktionen erfordern Login
GENERAL_MANAGER = {
    "DEFAULT_PERMISSIONS": {
        "READ":   ["isAuthenticated"],
        "CREATE": ["isAuthenticated"],
        "UPDATE": ["isAuthenticated"],
        "DELETE": ["isAuthenticated"],
    }
}
```

### Eingebaute Permission-Strings

| String                          | Bedingung                  | DB-Filter              |
| ------------------------------- | -------------------------- | ---------------------- |
| `public`                        | immer wahr                 | –                      |
| `isAuthenticated`               | `user.is_authenticated`    | –                      |
| `isActive`                      | `user.is_active`           | –                      |
| `isAdmin`                       | `user.is_staff`            | –                      |
| `isSelf`                        | `instance.creator == user` | `creator_id={user.id}` |
| `hasPermission:<perm>`          | `user.has_perm(perm)`      | –                      |
| `inGroup:<name>`                | User in Django-Gruppe      | –                      |
| `relatedUserField:<feld>`       | `instance.<feld> == user`  | `{feld}_id={user.id}`  |
| `manyToManyContainsUser:<feld>` | User in M2M-Feld           | `{feld}__id={user.id}` |
| `matches:<attr>:<wert>`         | `instance.<attr> == wert`  | `{attr}={wert}`        |

Superuser (`is_superuser=True`) umgehen alle Prüfungen.

### AND-Kombination

```python
__create__ = ["isAdmin&isActive"]   # beide müssen true sein
```

### Attribut-Level-Overrides

```python
class Permission(AdditiveManagerPermission):
    __read__ = ["public"]

    geheimes_feld = {
        "read":   ["isAdmin"],
        "update": ["isAdmin"],
        "delete": [],           # niemand darf löschen
    }
```

### Delegation via `__based_on__`

```python
class Position(GeneralManager):
    projekt: Projekt

    class Permission(AdditiveManagerPermission):
        __based_on__ = "projekt"   # delegiert Prüfung an Projekt-Permission
        __create__   = ["isAuthenticated"]  # zusätzliche Einschränkung
```

Wenn `__based_on__` gesetzt: **beide** Permissions (Basis + lokale) müssen True sein.
Ist das delegierte Objekt zur Laufzeit `None`, greift der globale Default.

### Custom Permissions registrieren (Forge-spezifisch)

```python
from general_manager.permission import register_permission


@register_permission("isProjektleiter")
def _permission_is_project_leader(instance, user, config) -> bool:
    return user.groups.filter(name="Projektleiter").exists()
```

Modul muss beim Django-Start importiert sein — am besten in `AppConfig.ready()` oder
als Import in `permission.py`, das von `apps.py` geladen wird.

### `CalculationPermission` (Forge-Pattern — in 0.45.0 noch nötig)

```python
class CalculationPermission(AdditiveManagerPermission):
    def get_read_permission_plan(self) -> ReadPermissionPlan:
        return ReadPermissionPlan(
            filters=[{"filter": {}, "exclude": {}}],
            requires_instance_check=False,
        )
```

Pflicht für jeden `CalculationInterface`-Manager: Der Instance-Check des Frameworks
ruft intern `queryset.filter(id__in=...)` auf, was für CalculationBuckets fehlschlägt
(`id` ist kein gültiges Filter-Feld). Ohne `CalculationPermission` liefern
`projektKennzahlenList`, `istWertList` etc. bei normalen Nutzern den Fehler
`Unknown input field 'id' in filter`.

**Verifiziert in 0.45.0:** Workaround ist weiterhin nötig. Jeder neue
`CalculationInterface`-GM muss `Permission = CalculationPermission` setzen
(oder eine eigene Subklasse, die `requires_instance_check=False` setzt).

---

## 6) Validators / Rules

Rules sind Validierungsregeln auf Modell-Ebene mit automatischen Fehlermeldungen
(via AST-Analyse der Funktion).

```python
from general_manager.rule import Rule


class Interface(DatabaseInterface):
    startdatum = models.DateField()
    enddatum   = models.DateField(null=True, blank=True)

    class Meta:
        rules = [
            Rule["Projekt"](lambda x: x.total_capex >= "0 EUR"),
            Rule["Projekt"](
                lambda order: order.quantity <= order.stock,
                custom_error_message="Bestellmenge ({quantity}) übersteigt Lager ({stock}).",
            ),
            Rule["Projekt"](
                lambda x: x.enddatum is None or x.startdatum <= x.enddatum,
                ignore_if_none=False,  # Prüfung auch bei None
            ),
        ]
```

Rules ignorieren `None`-Werte per Default (`ignore_if_none=True`). `ignore_if_none=False`
erzwingt Prüfung auch bei `None`.

Manuelle Evaluation (für Tests):

```python
result = my_rule.evaluate(instance)
if not result:
    print(my_rule.get_error_message())
```

Eingebaute AST-Handler: `len()`, `sum()`, `max()`, `min()` – erzeugen sprechende Fehlermeldungen.
Eigene Handler: `RULE_HANDLERS = ["myapp.rules.CustomHandler"]` in settings.py.

---

## 7) Factories & Seeding

### Factory-Definition

```python
from general_manager.factory import AutoFactory
import factory


class ProjektFactory(AutoFactory):
    interface = Projekt.Interface

    class Meta:
        model = Projekt.Interface._model

    name = "Default-Projekt"
    auftragsnummer = factory.Sequence(lambda n: f"2026-{n:03d}")
```

> `AutoFactory` wird für jeden Manager automatisch erstellt.
> Eigene Factories erben davon und überschreiben nur was nötig.

### Factory-Methoden

| Methode                      | Speichert in DB | Rückgabe      |
| ---------------------------- | --------------- | ------------- |
| `.build(**kwargs)`           | Nein            | Manager       |
| `.create(**kwargs)`          | Ja              | Manager       |
| `.build_batch(n, **kwargs)`  | Nein            | list[Manager] |
| `.create_batch(n, **kwargs)` | Ja              | list[Manager] |

### pytest-Integration

```python
import pytest


@pytest.fixture
def projekt(db):
    return ProjektFactory.create()
```

### Seeding (Entwicklungs-/Demo-Daten)

> **Command-Name:** Das Management-Command heißt **`seed_manager_landscape`**, nicht `seed`.
> (`python manage.py seed` wirft „Unknown command: 'seed'".)

```bash
python manage.py seed_manager_landscape                         # Standard-Counts
python manage.py seed_manager_landscape --all                   # alle Manager mit Factory.create_batch
python manage.py seed_manager_landscape --manager Projekt       # einzelner Manager (wiederholbar)
python manage.py seed_manager_landscape --target Projekt=20     # 20 Projekte sicherstellen (NAME=COUNT)
python manage.py seed_manager_landscape --count 10              # Default-Mindest-Count pro Manager
python manage.py seed_manager_landscape --batch-size 50         # Zeilen pro Transaktion
python manage.py seed_manager_landscape --continue-on-error     # Weiter auch bei Fehlern
python manage.py seed_manager_landscape --dry-run               # Was würde erstellt werden?
python manage.py seed_manager_landscape --output-format json    # Dry-run-Ausgabeformat
```

Seeding erzeugt nur **fehlende** Zeilen (min. target count). Wenn bereits genug
existieren, wird nichts erstellt. Abhängige Manager (ForeignKeys) müssen explizit
mit aufgeführt werden.

---

## 8) MeasurementField

`MeasurementField` speichert Messgrössen (physikalische Einheiten oder Währungen) typsicher.
Intern legt es **zwei gepaarte Datenbankspalten** an: ein DecimalField für den Wert
(`{feld}_value`) und ein CharField für die Einheit (`{feld}_unit`).

### Import

```python
from general_manager.measurement import Measurement, MeasurementField
```

### Felddefinition

```python
class Interface(DatabaseInterface):
    offerte_summe = MeasurementField(base_unit="CHF")
    gewicht       = MeasurementField(base_unit="kg", null=True, blank=True)
    dauer         = MeasurementField(base_unit="hour", null=True, blank=True)
```

> `base_unit` muss multiplikativ sein (keine Offset-Einheiten wie °C); andernfalls
> wirft das Feld einen `InvalidMeasurementFieldBaseUnitError`.

Typ-Annotationen auf der Manager-Klasse:

```python
class MeinManager(GeneralManager):
    offerte_summe:  Measurement
    gewicht:        Measurement | None
```

### Measurement-Objekte (Python)

```python
m = Measurement(100, "CHF")
m.magnitude   # Decimal('100')
m.unit        # 'CHF'

# Einheitenumrechnung (physikalisch)
Measurement(500, "cm").to("m")   # → Measurement(5, 'm')

# Arithmetik (gleiche Einheit)
Measurement(100, "CHF") + Measurement(50, "CHF")   # → Measurement(150, 'CHF')
```

### GraphQL – Output

```graphql
query {
  projekt(id: 1) {
    offerteSumme {
      value
      unit
    }
    gewicht(targetUnit: "g") {
      value
      unit
    }
  }
}
```

### GraphQL – Mutation (Input)

Measurement-Argumente werden als **String** `"<wert> <einheit>"` übergeben:

```graphql
mutation {
  createProjekt(offerteSumme: "50000 CHF") {
    success
  }
}
```

Im Frontend (TypeScript): `offerteSumme: \`${val.toFixed(2)} CHF\``

---

## 9) GraphQL-Integration

### Settings

Bevorzugt werden GM-Settings im `GENERAL_MANAGER`-Dict konfiguriert. Top-level-Settings
(`AUTOCREATE_GRAPHQL`, `GRAPHQL_URL`) funktionieren weiterhin als Legacy-Fallback — der
Lookup (`general_manager.conf.get_setting`) prüft in dieser Reihenfolge:
`GENERAL_MANAGER[<KEY>]` → `GENERAL_MANAGER_<KEY>` → top-level `<KEY>`.

```python
# Kanonische (bevorzugte) Form:
GENERAL_MANAGER = {
    "AUTOCREATE_GRAPHQL": True,
    "GRAPHQL_URL": "graphql/",
    "GRAPHQL_FILTER_RELATION_DEPTH": 1,   # Standard; Tiefe für Relation-Filter
    # Optional: eigene Directives
    "GRAPHQL_DIRECTIVES": [
        GraphQLDirective(name="scenario", locations=[DirectiveLocation.FIELD])
    ],
}

# Legacy (funktioniert ebenfalls, aber nicht die bevorzugte Stelle):
# AUTOCREATE_GRAPHQL = True
# GRAPHQL_URL = "graphql/"
```

Die `urls.py` braucht **keinen** manuellen GraphQL-Eintrag.

### Was automatisch generiert wird

- Pro GM-Klasse: `projekt(id: ...)` und `projektList(...)` Queries
- `@graph_ql_property`-Methoden → eigene Felder (sortable/filterable wenn deklariert)
- CRUD-Mutations: `createProjekt`, `updateProjekt`, `deleteProjekt`
- Subscription-Felder: `onProjektChange`, `onProjektClassChange`

### Namenskonventionen

| Python             | GraphQL                                                   |
| ------------------ | --------------------------------------------------------- |
| `offerte_summe`    | `offerteSumme` (camelCase)                                |
| `Projekt`          | Mutation-Rückgabe `Projekt` (Klassenname, Grossbuchstabe) |
| `ForeignKey`       | `String` (str() des Objekts)                              |
| `DecimalField`     | `Float`                                                   |
| `MeasurementField` | `MeasurementType { value unit }`                          |
| `BigAutoField`     | `BigIntScalar` via `graphql_scalar="bigint"` am Feld      |

> **Root-Felder sind camelCase (ab 0.42.1).** Auch mehrwortige Klassennamen werden
> konsistent camelCase exponiert: `IstWert` → `istWert` / `istWertList`,
> `ChangeRequestFeasibility` → `changeRequestFeasibility` / `changeRequestFeasibilityList`
> (nicht alles klein wie früher `changerequestfeasibilityList`).

### Query-Patterns

**Paginierte Liste:**

```graphql
query {
  projektList(
    page: 1
    pageSize: 20 # pageSize: 0 → nur pageInfo, keine Items
    orderBy: "-name" # "-" für absteigend
    includeInactive: true # nur bei use_soft_delete = True
  ) {
    items {
      id
      auftragsnummer
      offerteSumme {
        value
        unit
      }
    }
    pageInfo {
      totalCount
      totalPages
      currentPage
      pageSize
    }
  }
}
```

**Einzelnes Objekt:**

```graphql
query {
  projekt(id: 42) {
    auftragsnummer
    offerteSumme {
      value
      unit
    }
  }
}
```

**Mutation:**

```graphql
mutation {
  createProjekt(auftragsnummer: "2026-002", offerteSumme: "50000 CHF") {
    success
    errors
    Projekt {
      id
      auftragsnummer
    } # Klassenname mit Grossbuchstabe!
  }
}
```

### Relation-Filter

```graphql
# Direct-Relation (FK)
query {
  positionList(filter: { projekt: { auftragsnummer: "2026-001" } }) {
    items {
      id
    }
  }
}

# Collection (reverse FK / M2M) — any / none
query {
  projektList(filter: { positionen: { any: { status: "offen" } } }) {
    items {
      id
    }
  }
}
```

### Custom Mutations via `@graph_ql_mutation`

```python
from general_manager.api.mutation import graph_ql_mutation
from general_manager.permission.mutation_permission import MutationPermission
from typing import ClassVar


class PublishPermission(MutationPermission):
    __mutate__: ClassVar[list[str]] = ["isAuthenticated"]


@graph_ql_mutation(PublishPermission)
def publish_projekt(info, projekt_id: int, notiz: str | None = None) -> Projekt:
    # Erster Parameter 'info' = GraphQL ResolveInfo, wird NICHT als Argument exponiert
    projekt = Projekt(id=projekt_id)
    return projekt.update(
        status="published",
        notiz=notiz,
        creator_id=getattr(info.context.user, "id", None),
    )
```

- `info` als erster Parameter → kein GraphQL-Argument, nur Resolver-Context
- `str | None` → optionales Argument
- Rückgabe-Feld heisst `projekt` (Kleinbuchstabe aus Typ-Name)
- Tuple-Return für mehrere Payload-Felder: `-> tuple[PublishedProject, StatusMessage]`
- `ValidationError` und `ValueError` → `BAD_USER_INPUT` GraphQL-Fehler

---

## 10) GraphQL Subscriptions

Requires Django Channels mit konfiguriertem `CHANNEL_LAYERS`.

### Automatisch generierte Subscription-Felder

| Feld                   | Trigger                            |
| ---------------------- | ---------------------------------- |
| `onProjektChange`      | Änderung an einer Instanz (mit ID) |
| `onProjektClassChange` | Jede Änderung der Klasse (kein ID) |

```graphql
subscription {
  onProjektChange(id: 42) {
    action # "snapshot" | "update" | "delete"
    item {
      id
      bezeichnung
    }
  }
}
```

- `snapshot` → Initialzustand beim Aufbau
- `update` → nach create/update
- `delete` → nach delete; `item` ist null bei Hard-Delete
- Class-wide: kein initialer Snapshot; Permission-Check pro Event

---

## 11) Search

Volltext-Suche. Standard-Backend: `DevSearch` (in-memory). Produktiv: Meilisearch.
(Weitere Backends im Paket: Typesense, OpenSearch.)

```python
from general_manager import FieldConfig, IndexConfig


class Projekt(GeneralManager):
    class SearchConfig:
        indexes = [
            IndexConfig(
                name="global",
                fields=["bezeichnung", FieldConfig(name="projektleiter__name", boost=2.0)],
                filters=["status", "projektleiter_id"],
                sorts=["bezeichnung"],
                boost=1.2,
            )
        ]
```

```bash
python manage.py search_index --reindex          # Neuindizierung
python manage.py search_index --index global      # nur einen Index
python manage.py search_index --manager Projekt   # nur einen Manager
```

```graphql
query {
  search(query: "Lüftung" index: "global" types: ["Projekt"]) {
    items { ... }
    pageInfo { totalCount }
  }
}
```

---

## 12) Caching

### `@graph_ql_property` und Run-Cache

`@graph_ql_property` cached Ergebnisse standardmässig im **Run-Cache** (`cache="run"`):
der Cache wird für die Dauer eines GraphQL-Runs geteilt. Das verhindert doppelte
Berechnungen, wenn dasselbe Objekt mehrfach in einer Query auftaucht.

| Cache-Modus     | Decorator                                | Wann verwenden                                                  |
| --------------- | ---------------------------------------- | --------------------------------------------------------------- |
| `run` (Default) | `@graph_ql_property`                     | Alle Properties (ausreichend für DB-Zugriffe)                   |
| `dependency`    | `@graph_ql_property(cache="dependency")` | Request-übergreifend gecacht; invalidiert via DependencyTracker |
| `none`          | `@graph_ql_property(cache="none")`       | Sehr einfache/billige Properties                                |

> **Hinweis:** Gültige Modi für `@graph_ql_property` sind nur `run | dependency | none`.
> Der frühere `auto`-Modus existiert seit 0.42.0 nicht mehr. Den vierten Scope `timeout`
> gibt es ausschließlich beim eigenständigen `@cached`-Decorator (siehe unten).

### `@cached` Decorator (für eigene Funktionen)

> **Immer mit Klammern aufrufen: `@cached()`, nicht `@cached`.** Der erste
> Positionsparameter von `cached(...)` ist `timeout`, nicht die Funktion — bare `@cached`
> würde die Funktion fälschlich als `timeout` interpretieren und scheitert
> (in 0.45.0 mit `CacheTimeoutConfigurationError`, weil ein Nicht-None-`timeout` nur mit
> `scope="timeout"` erlaubt ist).

Signatur (sinngemäß): `cached(timeout=None, *, scope="run")`. Gültige Scopes:
`run | dependency | timeout | none`. Default ist `run`.

```python
from general_manager.cache.cache_decorator import cached


# Run-Scope (Default): memoiziert innerhalb des aktiven Run-Contexts,
# wird am Ende des Runs verworfen.
@cached()
def projekt_run_cache(projekt_id: int) -> dict:
    projekt = Projekt(id=projekt_id)
    return {"budget": projekt.offerte_summe.magnitude}


# Dependency-Scope: persistent im Cache-Backend, automatisch invalidiert,
# wenn ein gelesener Datensatz sich ändert (DependencyTracker). KEIN timeout erlaubt.
@cached(scope="dependency")
def projekt_forecast(projekt_id: int) -> dict:
    ...


# Timeout-Scope: TTL-basiert im Cache-Backend. timeout ist hier PFLICHT
# (und nur in diesem Scope erlaubt). Kein Dependency-Tracking.
@cached(scope="timeout", timeout=300)
def expensive_calc(projekt_id: int) -> float:
    ...


# Caching abschalten:
@cached(scope="none")
def always_fresh(projekt_id: int) -> float:
    ...
```

**Scope-Regeln (ab 0.43.0 strikt validiert):**

| Scope        | `timeout`        | Verhalten                                                        |
| ------------ | ---------------- | ---------------------------------------------------------------- |
| `run`        | nicht erlaubt    | Memoization im aktiven Run-Context, am Run-Ende verworfen        |
| `dependency` | nicht erlaubt    | Cache-Backend + Dependency-Tracking → automatische Invalidierung |
| `timeout`    | **erforderlich** | Cache-Backend mit TTL (Sekunden); kein Dependency-Tracking       |
| `none`       | nicht erlaubt    | Kein Caching                                                     |

> **Falsch (häufiger Irrtum):** `@cached(timeout=300)` ohne `scope="timeout"` wirft in
> 0.45.0 einen Fehler, weil `timeout` nur mit `scope="timeout"` kombinierbar ist.
> Ein eigenständiges `scoped_cache` gibt es **nicht** — "scoped caching" ist der
> `scope="run"`-Default von `@cached()`.

### DependencyTracker

```python
from general_manager.cache import DependencyTracker

with DependencyTracker() as dependencies:
    result = expensive_fn()
    # dependencies: Set[Dependency]
```

### Automatische Invalidierung

`create()`, `update()`, `delete()` emittieren Cache-Invalidierungssignale.
Alle mit `scope="dependency"` gecachten Funktionen, die den betreffenden Datensatz
gelesen haben, werden invalidiert.

**Produktion:** Geteiltes Cache-Backend (Redis) konfigurieren — der Dependency-Index
muss prozessübergreifend synchron sein.

---

## 13) History / Audit Trail

GeneralManager integriert `django-simple-history`. Automatisch hinzugefügte Felder:

| Feld                    | Bedeutung                                |
| ----------------------- | ---------------------------------------- |
| `history_date`          | Zeitstempel der Änderung                 |
| `history_user_id`       | User-ID (aus `creator_id`)               |
| `history_change_reason` | Kommentar (aus `history_comment`)        |
| `history_type`          | `+` (create), `~` (update), `-` (delete) |

```python
# Audit-Trail einer Instanz abfragen
projekt.history.all()
projekt.history.filter(history_change_reason__icontains="import")
projekt.history.order_by("-history_date").first()

# Point-in-time Bucket
stand = Projekt.filter(search_date=datetime(2026, 1, 1))
```

---

## 14) Observability / Logging

```python
# In settings.py aktivieren:
GENERAL_MANAGER = {
    "PERMISSION_AUDIT": True,
    # Logt: Akteur, Action-Typ, betroffene Attribute, Authorization-Outcome
    # Inkl. candidate/authorized/denied rows pro GraphQL-List-Query
}

LOGGING = {
    "loggers": {
        "general_manager": {"handlers": ["json_handler"], "level": "INFO"},
    }
}
```

Cache- und Mutation-Signale für eigene Pipelines:

```python
from general_manager.cache.signals import pre_data_change, post_data_change
```

---

## 15) RequestInterface

Für Manager, die Daten von externen HTTP-Services lesen (ohne lokale DB-Tabelle).

```python
from general_manager.interface import (
    BearerTokenAuthProvider, RequestField, RequestFilter,
    RequestInterface, RequestTransportConfig,
    RequestQueryOperation, UrllibRequestTransport,
)
from general_manager.manager.input import Input


class RemoteProjekt(GeneralManager):
    class Interface(RequestInterface):
        id     = Input(type=int)
        name   = RequestField(str)
        status = RequestField(str, source="state")

        class Meta:
            filters = {
                "status": RequestFilter(remote_name="state", value_type=str),
            }
            query_operations = {
                "list":   RequestQueryOperation(method="GET", path="/projects"),
                "detail": RequestQueryOperation(method="GET", path="/projects/{id}"),
            }
            transport        = UrllibRequestTransport()
            transport_config = RequestTransportConfig(
                base_url="https://service.example.com/api", timeout=10
            )
            auth_provider = BearerTokenAuthProvider(token=lambda: "token-here")
```

Nicht als generischen HTTP-Client verwenden — `RequestInterface` ist ressourcen-orientiert.

---

## 16) Workflow-Automation

Verbindet Manager-Events mit dauerhafter Automation.

```python
# settings.py
GENERAL_MANAGER = {
    # CRUD-Signale automatisch als Workflow-Events publizieren
    "WORKFLOW_SIGNAL_BRIDGE": True,
    # "WORKFLOW_ENGINE": "LocalWorkflowEngine"  # oder CeleryWorkflowEngine
}
```

Event-Routing via Registry:

```python
from general_manager.workflow import get_event_registry, manager_updated_event

registry = get_event_registry()
registry.register(
    event_type="general_manager.manager.updated",
    handler=my_handler,
    when=lambda event: event.manager_class == "Projekt",
)
```

Execution-States: `pending → running → completed/failed/cancelled` (+ `waiting` für async).

Management-Commands:

```bash
python manage.py workflow_drain_outbox          # ausstehende Events abarbeiten
python manage.py workflow_replay_dead_letters   # fehlgeschlagene nochmal versuchen
```

---

## 17) INSTALLED_APPS-Reihenfolge

> **Kritisch:** `django.contrib.admin` muss **vor** `general_manager` stehen.

```python
INSTALLED_APPS = [
    "daphne",
    "channels",
    "django.contrib.admin",   # VOR general_manager!
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "graphene_django",
    "general_manager",
    # ... eigene Apps ...
]

# GM-Settings bevorzugt im GENERAL_MANAGER-Dict (siehe Abschnitt 9):
GENERAL_MANAGER = {
    "AUTOCREATE_GRAPHQL": True,
    "GRAPHQL_URL": "graphql/",
}
```

---

## 18) CSRF & Frontend-Anbindung

```python
# forge/middleware.py
class DisableCSRFForGraphQL(MiddlewareMixin):
    def process_request(self, request):
        if request.path.startswith("/graphql"):
            setattr(request, "_dont_enforce_csrf_checks", True)

# settings.py
MIDDLEWARE = ["forge.middleware.DisableCSRFForGraphQL", ...]
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173"]
```

Apollo Client (TypeScript):

```typescript
const apolloClient = new ApolloClient({
  link: new HttpLink({ uri: "/graphql/" }),
  cache: new InMemoryCache(),
});
```

Vite-Proxy:

```typescript
server: { proxy: { "/graphql": "http://localhost:8000" } }
```

---

## 19) Häufige Gotchas

| Problem                                                 | Ursache                                                           | Lösung                                                                                                   |
| ------------------------------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `/admin/` → `NoReverseMatch: app_list`                  | `general_manager` vor `django.contrib.admin`                      | Django-Builtins zuerst (Abschnitt 17)                                                                    |
| `Bitte höchstens 2 Dezimalstellen`                      | GM gibt `float` ans Model; `DecimalField` → IEEE-754-Präzision    | `full_clean()` in Interface überschreiben (siehe unten)                                                  |
| `super()` in Interface-Methode schlägt fehl             | GM kopiert Methoden als plain functions; `__class__`-Cell falsch  | MRO manuell: `for cls in type(self).__mro__[1:]: if 'full_clean' in cls.__dict__: cls.full_clean(...)`   |
| `Unknown type 'Decimal'`                                | GM kennt keinen `Decimal`-Scalar                                  | `Float!` für DecimalField-Variablen, `String!` für MeasurementField                                      |
| `Cannot query field 'projekt'` auf Mutation             | Rückgabefeld = Klassenname (Grossbuchstabe)                       | `Projekt { ... }` statt `projekt { ... }`                                                                |
| `projektList` statt `projekt_list`                      | GM erzeugt camelCase                                              | Immer camelCase in GraphQL-Queries                                                                       |
| Mehrwort-Klasse → falsch geschriebenes Root-Feld        | Vor 0.42.1 wurden Root-Felder kleingeschrieben                    | camelCase nutzen: `IstWert` → `istWertList`, `ChangeRequestFeasibility` → `changeRequestFeasibilityList` |
| `items` statt `results` in Paginierung                  | GM nennt das Feld `items`                                         | `{ items { ... } pageInfo { totalCount } }`                                                              |
| `projektleiter { username }` schlägt fehl               | ForeignKey → `String` in GraphQL                                  | Kein Sub-Selection; direkt als String abfragen                                                           |
| CalculationInterface-Liste zeigt alle Daten             | `possible_values` gibt list() statt Bucket zurück                 | `possible_values=lambda: Manager.all()` — Bucket, kein `list(...)`                                       |
| `Input.monthly_date(year=...)` → `TypeError`            | Helfer nehmen `start`/`end` (date), kein `year`/`start_year`      | `Input.monthly_date(start=date(...), end=date(...))` (keyword-only)                                      |
| `@cached` ohne Klammern → Fehler                        | Erster Param ist `timeout`, nicht die Funktion                    | Immer `@cached()` schreiben                                                                              |
| `@cached(timeout=N)` → `CacheTimeoutConfigurationError` | `timeout` ist nur mit `scope="timeout"` erlaubt                   | `@cached(scope="timeout", timeout=N)`                                                                    |
| `scoped_cache` nicht importierbar                       | Es gibt kein `scoped_cache`                                       | `@cached(scope="run")` verwenden                                                                         |
| Property wird mehrfach berechnet                        | Private Methoden (`_helper()`) werden nicht vom run-cache erfasst | `@graph_ql_property` oder `@cached(scope="run")` auf Hilfsmethoden anwenden                              |
| `cache="auto"` Fehler                                   | Modus wurde in 0.42.0 entfernt                                    | Auf `cache="run"` (Default) oder `cache="dependency"` umstellen                                          |
| `Float cannot represent non numeric value`              | Frontend schickt String statt Zahl                                | `parseFloat(val.replace(",", "."))`                                                                      |
| Vite zeigt nichts im Container                          | Vite lauscht nur auf localhost                                    | `npm run dev -- --host`                                                                                  |

### Decimal-Float-Fix in Interface

```python
from decimal import Decimal
from typing import Any


def _normalize_decimal_fields(instance: Any, *field_names: str) -> None:
    for field_name in field_names:
        val = getattr(instance, field_name, None)
        if isinstance(val, float):
            setattr(instance, field_name, Decimal(str(val)))


def _call_parent_full_clean(instance: Any, *args: Any, **kwargs: Any) -> None:
    """super() funktioniert in Interface-Methoden nicht — MRO manuell durchlaufen."""
    for cls in type(instance).__mro__[1:]:
        if "full_clean" in cls.__dict__:
            cls.full_clean(instance, *args, **kwargs)
            return


class MeinModel(GeneralManager):
    wert: Decimal

    class Interface(DatabaseInterface):
        wert = models.DecimalField(max_digits=12, decimal_places=2)

        def full_clean(self, *args: Any, **kwargs: Any) -> None:
            _normalize_decimal_fields(self, "wert")
            _call_parent_full_clean(self, *args, **kwargs)
```

> **Tipp:** `MeasurementField` hat dieses Problem **nicht**.

---

## 20) Weiterführende Upstream-Doku

- Architecture: https://timkleindick.github.io/general_manager/concepts/architecture/
- Database Interfaces: https://timkleindick.github.io/general_manager/concepts/interfaces/db_based_interface/
- Computed Interfaces: https://timkleindick.github.io/general_manager/concepts/interfaces/computed_data_interfaces/
- Permissions: https://timkleindick.github.io/general_manager/concepts/permission/
- GraphQL Schema: https://timkleindick.github.io/general_manager/concepts/graphql/schema_autogen/
- Custom Mutations: https://timkleindick.github.io/general_manager/concepts/graphql/custom_mutations/
- Filtering & Pagination: https://timkleindick.github.io/general_manager/concepts/graphql/filters_pagination/
- Subscriptions: https://timkleindick.github.io/general_manager/concepts/graphql/subscriptions/
- Caching: https://timkleindick.github.io/general_manager/concepts/caching/
- Search: https://timkleindick.github.io/general_manager/concepts/search/
- Seeding: https://timkleindick.github.io/general_manager/concepts/seeding/
- Workflow: https://timkleindick.github.io/general_manager/concepts/workflow/
- RequestInterface: https://timkleindick.github.io/general_manager/concepts/interfaces/request_interface/
