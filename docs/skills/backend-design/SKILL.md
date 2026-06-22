# GeneralManager – Patterns & Konventionen für Forge

> Zweck: Lokale Referenz für Claude Code und Entwickler. Beschreibt die Patterns,
> Konventionen und Gotchas des GeneralManager-Frameworks, wie wir sie in Forge verwenden.
>
> Upstream-Doku: https://timkleindick.github.io/general_manager/
> Repo: https://github.com/TimKleindick/general_manager
> Aktuelle Version: 0.56.0
>
> Diese Doku wurde gegen den v0.56.0-Quellcode verifiziert (nicht nur gegen die Doku-Site).
> Versionshinweise im Text (z. B. „ab 0.50.0") markieren, in welchem Release sich ein
> Verhalten geändert hat.

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
12. [Caching & Warm-up](#12-caching--warm-up)
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

**Cache-Modus** (Default ist `run`; historisch wurde der frühere `auto`-Modus in 0.42.0
entfernt). `@graph_ql_property` und der eigenständige `@cached`-Decorator nutzen seit
0.50.0 dasselbe `cache=`-Keyword und dieselben vier Modi:

| Decorator                                          | Verhalten                                                               |
| -------------------------------------------------- | ----------------------------------------------------------------------- |
| `@graph_ql_property`                               | `cache="run"` (Default) — Ergebnis innerhalb eines GraphQL-Runs gecacht |
| `@graph_ql_property(cache="dependency")`           | Persistent gecacht, invalidiert wenn abhängige Manager sich ändern      |
| `@graph_ql_property(cache="timeout", timeout=300)` | Persistent mit TTL (Sekunden); `timeout` ist hier Pflicht (ab 0.50.0)   |
| `@graph_ql_property(cache="none")`                 | Kein Caching, bei sehr einfachen/billigen Properties                    |

Gültige Modi für `@graph_ql_property`: `run | dependency | timeout | none` (Default `run`).
Details zu den Modi und zum proaktiven `warm_up` in Abschnitt 12.

Für CalculationInterface-Properties mit DB-Zugriffen ist `cache="run"` (Default)
ausreichend — für teure Berechnungen, die Request-übergreifend gecacht werden sollen,
`cache="dependency"` (optional mit `warm_up=True`) verwenden.

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
Unveränderte Daten werden beim Sync übersprungen (ab 0.54.1). Write-Versuche zur
Laufzeit werfen Exceptions.

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
>
> **Ab 0.54.0:** `possible_values`-Callables werden pro Run gecacht (einmal ausgewertet
> und innerhalb des Runs wiederverwendet). Das Callable darf also ruhig etwas kosten —
> es läuft pro Enumeration nur einmal, nicht pro Kombination.

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

### Run-gecachte Indizes: `index_by` / `index_many` (ab 0.51.0)

Für rechenintensiven Code, der wiederholt nach einem Schlüssel in derselben Collection
sucht (z. B. Kennzahlen-Berechnungen, die pro Position/Rechnung nachschlagen), baut der
Bucket einen **run-gecachten** In-Memory-Index. Statt N-mal `filter(...)` aufzurufen,
einmal indexieren und dann per Dict-Lookup zugreifen:

```python
# Unique-Index: schluessel -> genau ein Manager (wirft bei Duplikat-Keys)
nach_konto = Lieferantenrechnung.filter(richtiger_titel=auftragsnummer).index_by("buchungskonto")
rechnung = nach_konto.get(konto)          # dict-Lookup, kein DB-Query

# Multi-Index: schluessel -> tuple[Manager, ...]
positionen_je_art = KostenPosition.filter(projekt=projekt).index_many("art")
for pos in positionen_je_art.get(art, ()):
    ...
```

- `index_by(key_spec, *, max_rows=1000)` → `dict[key, Manager]` (Unique; Duplikat-Key wirft `DuplicateBucketIndexKeyError`)
- `index_many(key_spec, *, max_rows=...)` → `dict[key, tuple[Manager, ...]]` (Mehrfach)
- Beide Ergebnisse werden **nur für den aktiven Calculation-Run** gecacht und mit
  Dependency-Tracking versehen (Invalidierung wie bei anderen Run-Caches).
- `max_rows` ist ein Guardrail; zu große Buckets werfen `BucketIndexTooLargeError`.

### Bucket-Dependency-Semantik (wichtig für Caching)

Dependency-Tracking erfolgt **lazy**: erst beim tatsächlichen Auswerten
(Iteration, `count()`, `first()`, `get()`, `bucket[0]`, `len()`, `in`),
nicht beim Konstruieren des Buckets. Verkettete `filter()`-Aufrufe werden
zu einem einzigen Dependency-Eintrag zusammengeführt.

> **Ab 0.48.0:** Innerhalb eines Runs werden Ergebnisse äquivalenter Bucket-Iterationen
> wiederverwendet — derselbe `filter(...)` zweimal im selben Run trifft beim zweiten Mal
> den Run-Cache statt erneut die DB. Für wiederholte _Lookups_ (nicht nur Iteration) ist
> `index_by`/`index_many` trotzdem die bessere Wahl.

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

### `CalculationPermission` (Forge-Pattern)

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

> **Versionsstand:** In 0.45.0 als weiterhin nötig verifiziert. Die 0.42.2-Änderung
> (`manager_id__in`-Filter im `filter_parser`) betrifft einen anderen Pfad als den
> Permission-Instance-Check (plain `id__in`), daher bleibt der Workaround auch in
> 0.45.0+ erforderlich. **Nach dem Upgrade auf 0.56.0 kurz gegenprüfen** (an _einem_
> Calculation-Manager `CalculationPermission` weglassen, List-Query mit aktiver
> Permission als normaler User ausführen) — dies ist Forge-Code, kein Framework-Code,
> und lässt sich nur am laufenden System sicher bestätigen.

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
# Konstruktor: Wert + Einheit (Wert wird zu Decimal koerziert)
m = Measurement(100, "CHF")
m.magnitude   # Decimal('100')
m.unit        # 'CHF'

# Einzel-String parsen → from_string (NICHT Measurement("50 cm"))
w = Measurement.from_string("50 cm")

# Einheitenumrechnung (physikalisch)
Measurement(500, "cm").to("m")   # → Measurement(5, 'm')

# Arithmetik (gleiche Einheit)
Measurement(100, "CHF") + Measurement(50, "CHF")   # → Measurement(150, 'CHF')
```

> **Achtung:** Für eine kombinierte „Wert+Einheit"-Zeichenkette `Measurement.from_string("50 cm")`
> verwenden. Der Zwei-Argument-Konstruktor `Measurement(50, "cm")` erwartet Wert und
> Einheit getrennt.

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

### Indexierung & Reconciliation (umgebaut in 0.55.0)

> **Wichtige Änderung:** Das frühere **request-getriggerte Auto-Reindex wurde entfernt**.
> Datenänderungen markieren betroffene Such-Indizes nur noch als **„dirty"**; das
> tatsächliche Reindexieren übernimmt ein **Reconciliation-Sweep**. Das hält Requests
> schnell und entkoppelt das Indexieren vom Write-Pfad.

```bash
# Voller / manueller (Neu-)Aufbau der Indizes:
python manage.py search_index --reindex          # alles neu indizieren
python manage.py search_index --index global      # nur einen Index
python manage.py search_index --manager Projekt   # nur einen Manager

# Reconciliation: nur die als "dirty" markierten Indizes abgleichen
python manage.py search_reconcile --once                 # ein Sweep, dann Ende
python manage.py search_reconcile --watch --interval 30  # Daemon-Modus, alle 30s
python manage.py search_reconcile --all                  # vorher ALLE States dirty markieren
python manage.py search_reconcile --limit 100            # max. States pro Sweep
```

In Produktion wird `search_reconcile` typischerweise per **Celery Beat** geplant
(periodischer Sweep), statt im Request-Pfad zu laufen. `search_index --reindex` bleibt
für vollständige Neuaufbauten (z. B. nach Schema-Änderung am Index).

```graphql
query {
  search(query: "Lüftung" index: "global" types: ["Projekt"]) {
    items { ... }
    pageInfo { totalCount }
  }
}
```

---

## 12) Caching & Warm-up

### `@graph_ql_property` und Run-Cache

`@graph_ql_property` cached Ergebnisse standardmässig im **Run-Cache** (`cache="run"`):
der Cache wird für die Dauer eines GraphQL-Runs geteilt. Das verhindert doppelte
Berechnungen, wenn dasselbe Objekt mehrfach in einer Query auftaucht.

| Cache-Modus     | Decorator                                          | Wann verwenden                                                  |
| --------------- | -------------------------------------------------- | --------------------------------------------------------------- |
| `run` (Default) | `@graph_ql_property`                               | Alle Properties (ausreichend für DB-Zugriffe)                   |
| `dependency`    | `@graph_ql_property(cache="dependency")`           | Request-übergreifend gecacht; invalidiert via DependencyTracker |
| `timeout`       | `@graph_ql_property(cache="timeout", timeout=300)` | Persistent mit TTL; `timeout` ist Pflicht (ab 0.50.0)           |
| `none`          | `@graph_ql_property(cache="none")`                 | Sehr einfache/billige Properties                                |

> **Hinweis:** Gültige Modi für `@graph_ql_property` sind `run | dependency | timeout | none`
> (Default `run`). Der frühere `auto`-Modus existiert seit 0.42.0 nicht mehr.

### Proaktiver Warm-up (ab 0.56.0)

Teure `dependency`- oder `timeout`-gecachte Properties können **proaktiv vorberechnet**
werden, statt erst lazy beim nächsten Request. Mit `warm_up=True` wird die Property nach
einer Invalidierung in eine Warm-up-Queue eingereiht und im Hintergrund neu berechnet —
der nächste echte Request trifft dann bereits einen warmen Cache.

```python
@graph_ql_property(cache="dependency", warm_up=True)
def teure_kennzahl(self) -> Measurement | None:
    ...
```

- `warm_up=True` erfordert `cache="dependency"` oder `cache="timeout"`
  (mit `cache="run"`/`"none"` → Fehler `warm_up=True requires cache="dependency" or cache="timeout"`).
- Die Warm-up-Tasks werden nach Invalidierung enqueued und über Celery abgearbeitet.

Management-Commands für den Warm-up:

```bash
python manage.py graphql_warmup                # ausstehende Warm-up-Rezepte abarbeiten
python manage.py graphql_warmup_refresh_due    # fällige timeout-gecachte Rezepte erneuern
```

In Produktion per Celery Beat planen (analog zu `search_reconcile`).

### `@cached` Decorator (für eigene Funktionen)

Signatur (sinngemäß): `cached(func=None, timeout=None, *, cache="run")`. Gültige
`cache`-Modi: `run | dependency | timeout | none`. Default ist `run`.

> **Ab 0.50.0:** Das Keyword heißt `cache=` (vorher `scope=`) — angeglichen an
> `@graph_ql_property`. Und **bare `@cached` (ohne Klammern) funktioniert jetzt**
> (vorher nötig: `@cached()`). Beide Schreibweisen sind gültig.

```python
from general_manager.cache.cache_decorator import cached


# Run-Scope (Default): memoiziert innerhalb des aktiven Run-Contexts,
# wird am Ende des Runs verworfen. Bare-Form ist ok:
@cached
def projekt_run_cache(projekt_id: int) -> dict:
    projekt = Projekt(id=projekt_id)
    return {"budget": projekt.offerte_summe.magnitude}


# Dependency-Scope: persistent im Cache-Backend, automatisch invalidiert,
# wenn ein gelesener Datensatz sich ändert (DependencyTracker). KEIN timeout erlaubt.
@cached(cache="dependency")
def projekt_forecast(projekt_id: int) -> dict:
    ...


# Timeout-Scope: TTL-basiert im Cache-Backend. timeout ist hier PFLICHT
# (und nur in diesem Scope erlaubt). Kein Dependency-Tracking.
@cached(cache="timeout", timeout=300)
def expensive_calc(projekt_id: int) -> float:
    ...


# Caching abschalten:
@cached(cache="none")
def always_fresh(projekt_id: int) -> float:
    ...
```

**Scope-Regeln (strikt validiert):**

| `cache`      | `timeout`        | Verhalten                                                        |
| ------------ | ---------------- | ---------------------------------------------------------------- |
| `run`        | nicht erlaubt    | Memoization im aktiven Run-Context, am Run-Ende verworfen        |
| `dependency` | nicht erlaubt    | Cache-Backend + Dependency-Tracking → automatische Invalidierung |
| `timeout`    | **erforderlich** | Cache-Backend mit TTL (Sekunden); kein Dependency-Tracking       |
| `none`       | nicht erlaubt    | Kein Caching                                                     |

> **Falsch (häufiger Irrtum):** `@cached(timeout=300)` ohne `cache="timeout"` wirft einen
> Fehler, weil `timeout` nur mit `cache="timeout"` kombinierbar ist
> (`timeout is only supported with cache="timeout"`).
> Ein eigenständiges `scoped_cache` gibt es **nicht** — "scoped caching" ist der
> `cache="run"`-Default von `@cached`.

### DependencyTracker

```python
from general_manager.cache import DependencyTracker

with DependencyTracker() as dependencies:
    result = expensive_fn()
    # dependencies: Set[Dependency]
```

### Automatische Invalidierung

`create()`, `update()`, `delete()` emittieren Cache-Invalidierungssignale.
Alle mit `cache="dependency"` gecachten Funktionen, die den betreffenden Datensatz
gelesen haben, werden invalidiert. (Properties mit `warm_up=True` werden danach
proaktiv neu berechnet — siehe oben.)

**Produktion:** Geteiltes Cache-Backend (Redis) konfigurieren — der Dependency-Index
muss prozessübergreifend synchron sein. (Intern ist der Dependency-Index ab 0.52.0
geshardet und die Invalidierung koordiniert; das ist für die Nutzung transparent.)

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

> **Verwandte periodische Commands (Celery Beat):** `search_reconcile` (Abschnitt 11)
> und `graphql_warmup` / `graphql_warmup_refresh_due` (Abschnitt 12).

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

| Problem                                                 | Ursache                                                           | Lösung                                                                                                                                                 |
| ------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/admin/` → `NoReverseMatch: app_list`                  | `general_manager` vor `django.contrib.admin`                      | Django-Builtins zuerst (Abschnitt 17)                                                                                                                  |
| `Bitte höchstens 2 Dezimalstellen`                      | GM gibt `float` ans Model; `DecimalField` → IEEE-754-Präzision    | `full_clean()` in Interface überschreiben (siehe unten)                                                                                                |
| `super()` in Interface-Methode schlägt fehl             | GM kopiert Methoden als plain functions; `__class__`-Cell falsch  | MRO manuell: `for cls in type(self).__mro__[1:]: if 'full_clean' in cls.__dict__: cls.full_clean(...)`                                                 |
| `Unknown type 'Decimal'`                                | GM kennt keinen `Decimal`-Scalar                                  | `Float!` für DecimalField-Variablen, `String!` für MeasurementField                                                                                    |
| `Cannot query field 'projekt'` auf Mutation             | Rückgabefeld = Klassenname (Grossbuchstabe)                       | `Projekt { ... }` statt `projekt { ... }`                                                                                                              |
| `projektList` statt `projekt_list`                      | GM erzeugt camelCase                                              | Immer camelCase in GraphQL-Queries                                                                                                                     |
| Mehrwort-Klasse → falsch geschriebenes Root-Feld        | Vor 0.42.1 wurden Root-Felder kleingeschrieben                    | camelCase nutzen: `IstWert` → `istWertList`, `ChangeRequestFeasibility` → `changeRequestFeasibilityList`                                               |
| `items` statt `results` in Paginierung                  | GM nennt das Feld `items`                                         | `{ items { ... } pageInfo { totalCount } }`                                                                                                            |
| `projektleiter { username }` schlägt fehl               | ForeignKey → `String` in GraphQL                                  | Kein Sub-Selection; direkt als String abfragen                                                                                                         |
| CalculationInterface-Liste zeigt alle Daten             | `possible_values` gibt list() statt Bucket zurück                 | `possible_values=lambda: Manager.all()` — Bucket, kein `list(...)`                                                                                     |
| `Input.monthly_date(year=...)` → `TypeError`            | Helfer nehmen `start`/`end` (date), kein `year`/`start_year`      | `Input.monthly_date(start=date(...), end=date(...))` (keyword-only)                                                                                    |
| `@cached(scope="run")` → `TypeError`                    | Keyword heißt seit 0.50.0 `cache=`, nicht `scope=`                | `@cached(cache="run")`                                                                                                                                 |
| `@cached(timeout=N)` → `CacheTimeoutConfigurationError` | `timeout` ist nur mit `cache="timeout"` erlaubt                   | `@cached(cache="timeout", timeout=N)`                                                                                                                  |
| `scoped_cache` nicht importierbar                       | Es gibt kein `scoped_cache`                                       | `@cached(cache="run")` verwenden                                                                                                                       |
| `warm_up=True requires cache=...`                       | `warm_up` braucht `dependency` oder `timeout`                     | `@graph_ql_property(cache="dependency", warm_up=True)`                                                                                                 |
| Property/Hilfsmethode wird mehrfach berechnet           | Private Methoden (`_helper()`) werden nicht vom run-cache erfasst | Abgeleitete `@graph_ql_property` _andere Properties_ lesen lassen, oder `@cached(cache="run")` auf Helfer; für wiederholte Lookups `bucket.index_by()` |
| `Measurement("50 cm")` liefert nicht das Erwartete      | Einzel-String → `from_string`, Konstruktor will Wert+Einheit      | `Measurement.from_string("50 cm")` bzw. `Measurement(50, "cm")`                                                                                        |
| Suche aktualisiert sich nicht nach Datenänderung        | Auto-Reindex wurde in 0.55.0 entfernt; Index ist nur "dirty"      | `search_reconcile` laufen lassen (manuell `--once` oder per Celery Beat)                                                                               |
| `cache="auto"` Fehler                                   | Modus wurde in 0.42.0 entfernt                                    | Auf `cache="run"` (Default) oder `cache="dependency"` umstellen                                                                                        |
| `Float cannot represent non numeric value`              | Frontend schickt String statt Zahl                                | `parseFloat(val.replace(",", "."))`                                                                                                                    |
| Vite zeigt nichts im Container                          | Vite lauscht nur auf localhost                                    | `npm run dev -- --host`                                                                                                                                |

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
