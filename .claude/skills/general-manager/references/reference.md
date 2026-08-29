# GeneralManager – Patterns & Konventionen für Forge

> Zweck: Lokale Referenz für Claude Code / Claude CLI und Entwickler. Beschreibt die
> Patterns, Konventionen und Gotchas des GeneralManager-Frameworks, wie wir sie in Forge
> verwenden.
>
> Upstream-Doku: https://timkleindick.github.io/general_manager/
> Repo: https://github.com/TimKleindick/general_manager
> Aktuelle Version: 0.76.0
>
> Diese Doku wurde gegen den v0.76.0-Quellcode verifiziert (nicht nur gegen die Doku-Site).
> Versionshinweise im Text (z. B. „ab 0.68.0") markieren, in welchem Release sich ein
> Verhalten geändert oder ein Feature Einzug gehalten hat.

---

## Inhaltsverzeichnis

1. [Architektur-Überblick](#1-architektur-überblick)
2. [Manager-Klassen definieren](#2-manager-klassen-definieren)
3. [CRUD-Operationen](#3-crud-operationen)
4. [Buckets (Collections)](#4-buckets-collections)
5. [Permissions (ABAC)](#5-permissions-abac)
6. [Validators / Rules](#6-validators--rules)
7. [Factories & Seeding](#7-factories--seeding)
8. [MeasurementField & DataFrames](#8-measurementfield--dataframes)
9. [GraphQL-Integration](#9-graphql-integration)
10. [GraphQL Subscriptions](#10-graphql-subscriptions)
11. [Search](#11-search)
12. [Caching & Warm-up](#12-caching--warm-up)
13. [History, Audit & Temporale Abfragen (As-of)](#13-history-audit--temporale-abfragen-as-of)
14. [Observability / Logging](#14-observability--logging)
15. [RequestInterface](#15-requestinterface)
16. [Workflow-Automation](#16-workflow-automation)
17. [File-Uploads](#17-file-uploads)
18. [Chat / NLI-Subsystem](#18-chat--nli-subsystem)
19. [INSTALLED_APPS-Reihenfolge](#19-installed_apps-reihenfolge)
20. [CSRF & Frontend-Anbindung](#20-csrf--frontend-anbindung)
21. [Häufige Gotchas](#21-häufige-gotchas)
22. [Weiterführende Upstream-Doku](#22-weiterführende-upstream-doku)

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
  Unterstützt `filter()`, `exclude()`, `sort()`, `group_by()`, Union (`|`),
  Projektionen (`values()`/`values_list()`) und run-gecachte Indizes (`index_by()`). Lazy.
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

> **Wichtig (ab 0.68.0): `@graph_ql_property` verlangt eine Return-Annotation.**
> Ohne `-> Typ` wirft der Decorator `GraphQLPropertyReturnAnnotationError`. Die Annotation
> steuert den generierten GraphQL-Ausgabetyp — inklusive **strukturierter Ausgabe-Objekttypen**
> (nicht nur Scalars/Measurement): Gibt eine Property z. B. eine annotierte Struktur zurück,
> generiert GM daraus einen GraphQL-Objekttyp (`GraphQLType`).

```python
from general_manager.api.property import graph_ql_property


class Projekt(GeneralManager):
    startdatum: date
    enddatum: date | None

    @graph_ql_property
    def dauer_tage(self) -> int | None:          # Return-Annotation PFLICHT
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

| Decorator                                            | Verhalten                                                                |
| ---------------------------------------------------- | ------------------------------------------------------------------------ |
| `@graph_ql_property`                                 | `cache="run"` (Default) — Ergebnis innerhalb eines GraphQL-Runs gecacht  |
| `@graph_ql_property(cache="dependency")`             | Persistent gecacht, invalidiert wenn abhängige Manager sich ändern       |
| `@graph_ql_property(cache="timeout", timeout=300)`   | Persistent mit TTL (Sekunden); `timeout` ist hier Pflicht (ab 0.50.0)    |
| `@graph_ql_property(cache="none")`                   | Kein Caching, bei sehr einfachen/billigen Properties                     |

Gültige Modi: `run | dependency | timeout | none` (Default `run`). Für teure Properties
zusätzlich `warm_up=True` (proaktiver Warm-up nach Invalidierung; braucht `cache="dependency"`
oder `"timeout"`) — Details in Abschnitt 12.

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
> Eine reine Liste hat kein `.filter()` und kann beim Auflisten nicht per `.filter(id=...)`
> eingegrenzt werden — die Query liefert dann alle Werte.
>
> ```python
> # SCHLECHT – list() kann nicht gefiltert werden
> projekt = Input(Projekt, possible_values=lambda: list(Projekt.all()))
> # GUT – Filter wird als .filter(id=1) angewendet
> projekt = Input(Projekt, possible_values=lambda: Projekt.all())
> ```
>
> **Ab 0.54.0:** `possible_values`-Callables werden pro Run gecacht (einmal ausgewertet,
> innerhalb des Runs wiederverwendet).

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
projekt.update(creator_id=request.user.id, bezeichnung="Lüftung Rohbau – Phase 2")
# projekt.bezeichnung ist danach sofort aktuell

# Löschen (invalidiert die Instanz für weitere Attributzugriffe)
projekt.delete(creator_id=request.user.id, history_comment="Projekt storniert")
```

### Lesen: `get`-Shortcut (ab 0.44.0)

`Manager.get(**kwargs)` ist ein Convenience-Wrapper für `filter(**kwargs).get()`:

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
offene  = Projekt.filter(projekt_status__name="Offen")
exkl    = Projekt.exclude(status="archiviert")
kombi   = offene | exkl   # Union (OR)
```

### Filtern & Ausschliessen

Unterstützt Django ORM-Lookups: `__exact`, `__icontains`, `__gte`, `__lte`,
`__in`, `__range`, `__isnull`, `__startswith`, …

```python
bucket.filter(name__icontains="test", startdatum__gte=date(2026, 1, 1),
              status__in=["active", "pending"])
bucket.exclude(deleted=True)
bucket.filter(...).filter(...).exclude(...)     # Chaining
```

Historische (Point-in-time) Abfragen: siehe Abschnitt 13 (As-of).

### Sortieren

```python
bucket.sort("name")              # aufsteigend
bucket.sort("-startdatum")       # absteigend
bucket.sort(("-datum", "name"))  # mehrere Felder
bucket.sort("projekt__name")     # Relation-Pfad (ab 0.7x) — über FK sortieren
```

> **Ab 0.7x:** Sortierung über Relation-Pfade (`relation__feld`) wird unterstützt, auch
> für In-Memory-Buckets; zusammengesetzte GraphQL-Sort-Keys werden normalisiert.

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

### Projektionen: `values()` / `values_list()` (ab 0.7x)

Django-QuerySet-artige Projektionen — geben losgelöste Werte statt Manager-Instanzen
zurück (praktisch für Reports/Exporte). Pro Run gecacht.

```python
# Liste von Dicts für ausgewählte öffentliche Felder
rows = Projekt.all().values("auftragsnummer", "bezeichnung")
# → ({"auftragsnummer": "2026-001", "bezeichnung": "..."}, ...)

# Tupel-Zeilen
tuples = Projekt.all().values_list("auftragsnummer", "bezeichnung")
# Flache Tupel bei genau einem Feld:
nummern = Projekt.all().values_list("auftragsnummer", flat=True)
```

Unbekannte/duplizierte Felder werfen `UnknownProjectionFieldError` /
`DuplicateProjectionFieldError`; `flat=True` mit mehr als einem Feld wirft
`FlatProjectionFieldCountError`.

### Run-gecachte Indizes: `index_by` / `index_many` (ab 0.51.0)

Für rechenintensiven Code, der wiederholt nach einem Schlüssel in derselben Collection
sucht (z. B. Kennzahlen, die pro Position/Rechnung nachschlagen). Statt N-mal `filter(...)`
einmal indexieren, dann per Dict-Lookup zugreifen:

```python
# Unique-Index: schluessel -> genau ein Manager (wirft bei Duplikat-Keys)
nach_konto = Lieferantenrechnung.filter(richtiger_titel=nr).index_by("buchungskonto")
rechnung = nach_konto.get(konto)          # Dict-Lookup, kein DB-Query

# Multi-Index: schluessel -> tuple[Manager, ...]
positionen_je_art = KostenPosition.filter(projekt=projekt).index_many("art")
for pos in positionen_je_art.get(art, ()):
    ...
```

- `index_by(key_spec, *, max_rows=1000)` → `dict[key, Manager]` (Unique; Duplikat wirft `DuplicateBucketIndexKeyError`)
- `index_many(key_spec, *, max_rows=...)` → `dict[key, tuple[Manager, ...]]`
- Beide Ergebnisse werden **nur für den aktiven Calculation-Run** gecacht (mit Dependency-Tracking).
- `max_rows` ist ein Guardrail; zu große Buckets werfen `BucketIndexTooLargeError`.

### Bucket-Dependency-Semantik (wichtig für Caching)

Dependency-Tracking erfolgt **lazy**: erst beim tatsächlichen Auswerten
(Iteration, `count()`, `first()`, `get()`, `bucket[0]`, `len()`, `in`, `values()`),
nicht beim Konstruieren. Verkettete `filter()` werden zu einem Dependency-Eintrag
zusammengeführt.

> **Ab 0.48.0:** Innerhalb eines Runs werden Ergebnisse äquivalenter Bucket-Iterationen
> wiederverwendet (derselbe `filter(...)` zweimal → zweiter Zugriff trifft den Run-Cache).
> Für wiederholte *Lookups* ist `index_by`/`index_many` trotzdem die bessere Wahl.

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

- `AdditiveManagerPermission`: Attribut-Regel wird **zusätzlich** zur Klassen-Regel geprüft (AND).
- `OverrideManagerPermission`: Attribut-Regel **ersetzt** die Klassen-Regel für dieses Feld.
- `ManagerBasedPermission` ist ein veralteter, abwärtskompatibler Alias von `AdditiveManagerPermission` — nicht mehr verwenden.

> **Ab 0.7x:** Statische Permission-Pläne (Regeln ohne Instance-Bezug wie `public`,
> `isAuthenticated`) werden für List-/Search-Queries kurzgeschlossen (Performance). Für die
> Nutzung ändert sich nichts — die Regeln bleiben identisch.

### Defaults aus Settings

```python
# Forge settings.py — alle Aktionen erfordern Login
GENERAL_MANAGER = {
    "DEFAULT_PERMISSIONS": {
        "READ": ["isAuthenticated"], "CREATE": ["isAuthenticated"],
        "UPDATE": ["isAuthenticated"], "DELETE": ["isAuthenticated"],
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

Superuser (`is_superuser=True`) umgehen alle Prüfungen. AND-Kombination: `["isAdmin&isActive"]`.

### Attribut-Level-Overrides

```python
class Permission(AdditiveManagerPermission):
    __read__ = ["public"]
    geheimes_feld = {"read": ["isAdmin"], "update": ["isAdmin"], "delete": []}
```

### Delegation via `__based_on__`

```python
class Position(GeneralManager):
    projekt: Projekt
    class Permission(AdditiveManagerPermission):
        __based_on__ = "projekt"            # delegiert an Projekt-Permission
        __create__   = ["isAuthenticated"]  # zusätzliche Einschränkung
```

Wenn `__based_on__` gesetzt: **beide** Permissions müssen True sein. Ist das delegierte
Objekt zur Laufzeit `None`, greift der globale Default.

### Custom Permissions registrieren (Forge-spezifisch)

```python
from general_manager.permission import register_permission

@register_permission("isProjektleiter")
def _permission_is_project_leader(instance, user, config) -> bool:
    return user.groups.filter(name="Projektleiter").exists()
```

Modul muss beim Django-Start importiert sein — am besten in `AppConfig.ready()` oder als
Import in `permission.py`, das von `apps.py` geladen wird.

### `CalculationPermission` (Forge-Pattern)

```python
class CalculationPermission(AdditiveManagerPermission):
    def get_read_permission_plan(self) -> ReadPermissionPlan:
        return ReadPermissionPlan(
            filters=[{"filter": {}, "exclude": {}}],
            requires_instance_check=False,
        )
```

Pflicht für jeden `CalculationInterface`-Manager: Der Instance-Check ruft intern
`queryset.filter(id__in=...)` auf, was für CalculationBuckets fehlschlägt (`id` ist kein
gültiges Filter-Feld). Ohne `CalculationPermission` liefern `projektKennzahlenList`,
`istWertList` etc. bei normalen Nutzern `Unknown input field 'id' in filter`.

> **Versionsstand:** In 0.45.0 als weiterhin nötig verifiziert. Die statischen
> Permission-Optimierungen ab 0.7x betreffen den Kurzschluss-Pfad, nicht den
> id-Instance-Check auf Calculation-Buckets. **Nach dem Upgrade auf 0.76.0 kurz
> gegenprüfen** (an *einem* Calculation-Manager `CalculationPermission` weglassen,
> List-Query als normaler User ausführen) — dies ist Forge-Code, kein Framework-Code,
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

> **Custom-Message-Templates (ab 0.7x):** `custom_error_message` unterstützt **dotted
> Placeholders** (z. B. `{order.kunde.name}`) und wird **beim Start validiert** — ungültige
> Placeholder-Pfade werfen früh statt zur Laufzeit. Die frühere Pflicht, *alle* Variablen des
> Prädikats zu referenzieren, wurde gelockert; du kannst also gezielt einzelne Werte einsetzen.

Manuelle Evaluation (für Tests):

```python
result = my_rule.evaluate(instance)
if not result:
    print(my_rule.get_error_message())
```

Eingebaute AST-Handler: `len()`, `sum()`, `max()`, `min()`. Eigene Handler:
`RULE_HANDLERS = ["myapp.rules.CustomHandler"]` in settings.py.

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

```bash
python manage.py seed_manager_landscape                         # Standard-Counts
python manage.py seed_manager_landscape --all                   # alle Manager
python manage.py seed_manager_landscape --manager Projekt       # einzelner Manager
python manage.py seed_manager_landscape --target Projekt=20     # NAME=COUNT sicherstellen
python manage.py seed_manager_landscape --count 10              # Default-Mindest-Count
python manage.py seed_manager_landscape --batch-size 50         # Zeilen pro Transaktion
python manage.py seed_manager_landscape --continue-on-error     # Weiter bei Fehlern
python manage.py seed_manager_landscape --dry-run               # Was würde erstellt?
python manage.py seed_manager_landscape --output-format json    # Dry-run-Ausgabeformat
```

Seeding erzeugt nur **fehlende** Zeilen (min. target count). Abhängige Manager
(ForeignKeys) müssen explizit mit aufgeführt werden.

---

## 8) MeasurementField & DataFrames

`MeasurementField` speichert Messgrössen (physikalische Einheiten oder Währungen) typsicher.
Intern legt es **zwei gepaarte Datenbankspalten** an: ein DecimalField für den Wert
(`{feld}_value`) und ein CharField für die Einheit (`{feld}_unit`).

### Import & Felddefinition

```python
from general_manager.measurement import Measurement, MeasurementField

class Interface(DatabaseInterface):
    offerte_summe = MeasurementField(base_unit="CHF")
    gewicht       = MeasurementField(base_unit="kg", null=True, blank=True)
    dauer         = MeasurementField(base_unit="hour", null=True, blank=True)
```

> `base_unit` muss multiplikativ sein (keine Offset-Einheiten wie °C); andernfalls
> `InvalidMeasurementFieldBaseUnitError`.

Typ-Annotationen auf der Manager-Klasse: `offerte_summe: Measurement`, `gewicht: Measurement | None`.

### Measurement-Objekte (Python)

```python
# Konstruktor: Wert + Einheit (Wert wird zu Decimal koerziert)
m = Measurement(100, "CHF")
m.magnitude   # Decimal('100')
m.unit        # 'CHF'

# Einzel-String parsen → from_string (NICHT Measurement("50 cm"))
w = Measurement.from_string("50 cm")

Measurement(500, "cm").to("m")                     # Umrechnung → Measurement(5, 'm')
Measurement(100, "CHF") + Measurement(50, "CHF")   # Arithmetik → Measurement(150, 'CHF')
```

> **Achtung:** Für eine kombinierte „Wert+Einheit"-Zeichenkette `Measurement.from_string("50 cm")`
> verwenden. Der Zwei-Argument-Konstruktor `Measurement(50, "cm")` erwartet Wert und Einheit getrennt.

### GraphQL – Output / Mutation

```graphql
query   { projekt(id: 1) { offerteSumme { value unit } gewicht(targetUnit: "g") { value unit } } }
mutation { createProjekt(offerteSumme: "50000 CHF") { success } }   # Input als String
```

Im Frontend (TypeScript): `offerteSumme: \`${val.toFixed(2)} CHF\``

### Pandas-DataFrame-Export (ab 0.7x)

GM bringt optionale Helfer, um Zeilen mit Measurement-Feldern in eine **pandas DataFrame**
zu expandieren und zurück. Für dich als Data Analyst der direkte Weg von GM-Daten in die
Analyse. **`pandas` ist eine optionale Dependency** — ist es nicht installiert, werfen die
Helfer beim Aufruf.

```python
from general_manager.dataframes import to_dataframe, from_dataframe

# Zeilen (Mappings/Dicts) → DataFrame; Measurement-Felder werden in
# value/unit-Spalten expandiert (z. B. offerte_summe_value / offerte_summe_unit):
rows = Projekt.all().values("auftragsnummer", "offerte_summe")   # Projektion (Abschnitt 4)
df = to_dataframe(rows, measurement_fields=["offerte_summe"])

# Zurück: value/unit-Spalten wieder zu Measurement kollabieren
records = from_dataframe(df, measurement_fields=["offerte_summe"])
```

- `to_dataframe(rows, *, measurement_fields=None, **dataframe_kwargs)` → `pandas.DataFrame`
- `from_dataframe(dataframe, *, measurement_fields)` → `list[dict]`
- Für den Round-Trip in beiden Richtungen dieselben `measurement_fields` angeben. Kollision
  mit bestehenden Spaltennamen wirft `MeasurementDataFrameColumnCollisionError`; fehlende
  erwartete Spalten `MissingMeasurementDataFrameColumnError`.

---

## 9) GraphQL-Integration

### Settings

Bevorzugt im `GENERAL_MANAGER`-Dict. Top-level `AUTOCREATE_GRAPHQL`/`GRAPHQL_URL` funktionieren
als Legacy-Fallback — Lookup-Reihenfolge (`general_manager.conf.get_setting`):
`GENERAL_MANAGER[<KEY>]` → `GENERAL_MANAGER_<KEY>` → top-level `<KEY>`.

```python
GENERAL_MANAGER = {
    "AUTOCREATE_GRAPHQL": True,
    "GRAPHQL_URL": "graphql/",
    "GRAPHQL_FILTER_RELATION_DEPTH": 1,     # Standard; Tiefe für Relation-Filter
    "GRAPHQL_DIRECTIVES": [                  # optional eigene Directives
        GraphQLDirective(name="scenario", locations=[DirectiveLocation.FIELD])
    ],
}
```

Die `urls.py` braucht **keinen** manuellen GraphQL-Eintrag.

### Was automatisch generiert wird

- Pro GM-Klasse: `projekt(id: ...)` und `projektList(...)` Queries
- `@graph_ql_property`-Methoden → eigene Felder (sortable/filterable wenn deklariert)
- **Strukturierte Ausgabetypen (ab 0.68.0):** Gibt eine Property einen annotierten
  strukturierten Typ zurück, generiert GM daraus einen GraphQL-Objekttyp (`GraphQLType`) —
  nicht nur Scalars. Deshalb ist die Return-Annotation Pflicht (Abschnitt 2).
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

> **Root-Felder sind camelCase (ab 0.42.1).** Auch mehrwortige Klassennamen:
> `IstWert` → `istWert` / `istWertList`, `ChangeRequestFeasibility` → `changeRequestFeasibilityList`.

### Query-Patterns

```graphql
# Paginierte Liste
query {
  projektList(
    page: 1
    pageSize: 20            # pageSize: 0 → nur pageInfo, keine Items
    orderBy: "-name"        # "-" für absteigend
    includeInactive: true   # nur bei use_soft_delete = True
  ) {
    items { id auftragsnummer offerteSumme { value unit } }
    pageInfo { totalCount totalPages currentPage pageSize }
  }
}

# Einzelnes Objekt
query { projekt(id: 42) { auftragsnummer offerteSumme { value unit } } }

# Mutation — Rückgabefeld = Klassenname (Grossbuchstabe!)
mutation {
  createProjekt(auftragsnummer: "2026-002", offerteSumme: "50000 CHF") {
    success errors Projekt { id auftragsnummer }
  }
}
```

### Relation-Filter

```graphql
# Direct-Relation (FK)
query { positionList(filter: { projekt: { auftragsnummer: "2026-001" } }) { items { id } } }
# Collection (reverse FK / M2M) — any / none
query { projektList(filter: { positionen: { any: { status: "offen" } } }) { items { id } } }
```

### Fehler-Contract (ab 0.7x)

GM hat einen **expliziten öffentlichen GraphQL-Fehler-Contract**: erwartbare Fehler werden
als `PublicGraphQLError` mit strukturierten Validierungsfehlern zurückgegeben (statt roher
Interna). `ValidationError` / `ValueError` in Resolvern/Mutations → `BAD_USER_INPUT`.
Im Frontend die strukturierten `errors` auswerten statt Strings zu parsen.

### Custom Mutations via `@graph_ql_mutation`

```python
from general_manager.api.mutation import graph_ql_mutation
from general_manager.permission.mutation_permission import MutationPermission
from typing import ClassVar


class PublishPermission(MutationPermission):
    __mutate__: ClassVar[list[str]] = ["isAuthenticated"]


@graph_ql_mutation(PublishPermission)
def publish_projekt(info, projekt_id: int, notiz: str | None = None) -> Projekt:
    # 'info' (erster Parameter) = GraphQL ResolveInfo, wird NICHT als Argument exponiert
    projekt = Projekt(id=projekt_id)
    return projekt.update(status="published", notiz=notiz,
                          creator_id=getattr(info.context.user, "id", None))
```

- `info` als erster Parameter → kein GraphQL-Argument, nur Resolver-Context
- `str | None` → optionales Argument; Rückgabe-Feld = Kleinbuchstabe des Typnamens (`projekt`)
- Tuple-Return für mehrere Payload-Felder: `-> tuple[PublishedProject, StatusMessage]`

---

## 10) GraphQL Subscriptions

Requires Django Channels mit konfiguriertem `CHANNEL_LAYERS`.

| Feld                   | Trigger                            |
| ---------------------- | ---------------------------------- |
| `onProjektChange`      | Änderung an einer Instanz (mit ID) |
| `onProjektClassChange` | Jede Änderung der Klasse (kein ID) |

```graphql
subscription {
  onProjektChange(id: 42) {
    action          # "snapshot" | "update" | "delete"
    item { id bezeichnung }
  }
}
```

- `snapshot` (Initialzustand), `update` (nach create/update), `delete` (`item` null bei Hard-Delete)
- Class-wide: kein initialer Snapshot; Permission-Check pro Event

> **Batching (ab 0.7x):** Datenänderungen können als gebündelte Refresh-Events geliefert
> werden; Bulk-Operationen fassen Benachrichtigungen in einem Batch-Kontext zusammen
> (`bulk_data_change_notifications`), statt pro Zeile ein Event zu feuern.

---

## 11) Search

Volltext-Suche. Standard-Backend: `DevSearch` (in-memory). Produktiv: Meilisearch.
(Weitere Backends: Typesense, OpenSearch.)

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

> **Wichtig:** Das request-getriggerte Auto-Reindex wurde entfernt. Datenänderungen
> markieren Indizes nur noch als **„dirty"**; ein **Reconciliation-Sweep** reindexiert sie.

```bash
python manage.py search_index --reindex          # voller / manueller (Neu-)Aufbau
python manage.py search_index --manager Projekt   # nur ein Manager
python manage.py search_reconcile --once                 # ein Sweep, dann Ende
python manage.py search_reconcile --watch --interval 30  # Daemon, alle 30s
python manage.py search_reconcile --all                  # vorher ALLE States dirty markieren
python manage.py search_reconcile --limit 100            # max. States pro Sweep
```

In Produktion `search_reconcile` per **Celery Beat** planen. `search_index --reindex` bleibt
für vollständige Neuaufbauten.

### Deklarative Invalidierungs-Regeln (ab 0.7x)

Zusätzlich zu Feldern lässt sich deklarativ steuern, **welche Datenänderungen** einen Index
dirty machen — inkl. verwandter Objekte und M2M-Beziehungen (`SearchInvalidationRule`,
`SearchChange` aus `general_manager.search.config`). Damit werden auch Änderungen an
referenzierten Managern korrekt als Reindex-Anlass erkannt, gebündelt in beschränkten Batches.

```graphql
query { search(query: "Lüftung", index: "global", types: ["Projekt"]) {
  items { ... } pageInfo { totalCount } } }
```

---

## 12) Caching & Warm-up

### `@graph_ql_property` und Run-Cache

Default `cache="run"`: geteilt für die Dauer eines GraphQL-Runs (verhindert Doppel-Berechnung
desselben Objekts in einer Query).

| Cache-Modus     | Decorator                                          | Wann verwenden                                                  |
| --------------- | -------------------------------------------------- | --------------------------------------------------------------- |
| `run` (Default) | `@graph_ql_property`                               | Alle Properties (ausreichend für DB-Zugriffe)                   |
| `dependency`    | `@graph_ql_property(cache="dependency")`           | Request-übergreifend gecacht; invalidiert via DependencyTracker |
| `timeout`       | `@graph_ql_property(cache="timeout", timeout=300)` | Persistent mit TTL; `timeout` ist Pflicht                       |
| `none`          | `@graph_ql_property(cache="none")`                 | Sehr einfache/billige Properties                                |

### Proaktiver Warm-up (ab 0.56.0)

Teure `dependency`-/`timeout`-Properties per `warm_up=True` proaktiv vorberechnen (statt lazy
beim nächsten Request):

```python
@graph_ql_property(cache="dependency", warm_up=True)
def teure_kennzahl(self) -> Measurement | None:
    ...
```

- `warm_up=True` erfordert `cache="dependency"` oder `"timeout"` (sonst `GraphQLPropertyWarmUpConfigurationError`).
- Warm-up-Tasks werden nach Invalidierung enqueued und über Celery abgearbeitet:

```bash
python manage.py graphql_warmup                # ausstehende Warm-up-Rezepte abarbeiten
python manage.py graphql_warmup_refresh_due    # fällige timeout-gecachte Rezepte erneuern
```

### `@cached` Decorator (für eigene Funktionen)

Signatur (sinngemäß): `cached(func=None, timeout=None, *, cache="run")`. Modi:
`run | dependency | timeout | none` (Default `run`).

> **Ab 0.50.0:** Keyword heißt `cache=` (vorher `scope=`), und **bare `@cached` funktioniert**
> (vorher `@cached()` nötig). Beide Schreibweisen gültig.

```python
from general_manager.cache.cache_decorator import cached

@cached                                  # Run-Scope (Default), bare-Form ok
def a(projekt_id: int) -> dict: ...

@cached(cache="dependency")              # persistent + Dependency-Invalidierung; KEIN timeout
def b(projekt_id: int) -> dict: ...

@cached(cache="timeout", timeout=300)    # TTL; timeout PFLICHT und nur hier erlaubt
def c(projekt_id: int) -> float: ...

@cached(cache="none")                    # kein Caching
def d(projekt_id: int) -> float: ...
```

| `cache`      | `timeout`        | Verhalten                                                        |
| ------------ | ---------------- | ---------------------------------------------------------------- |
| `run`        | nicht erlaubt    | Memoization im aktiven Run-Context, am Run-Ende verworfen        |
| `dependency` | nicht erlaubt    | Cache-Backend + Dependency-Tracking → automatische Invalidierung |
| `timeout`    | **erforderlich** | Cache-Backend mit TTL (Sekunden); kein Dependency-Tracking       |
| `none`       | nicht erlaubt    | Kein Caching                                                     |

> **Falsch:** `@cached(timeout=300)` ohne `cache="timeout"` wirft
> (`timeout is only supported with cache="timeout"`). Ein `scoped_cache` gibt es **nicht** —
> "scoped caching" ist der `cache="run"`-Default.

### DependencyTracker & Invalidierung

```python
from general_manager.cache import DependencyTracker
with DependencyTracker() as dependencies:
    result = expensive_fn()   # dependencies: Set[Dependency]
```

`create()/update()/delete()` emittieren Invalidierungssignale; alle `cache="dependency"`-Funktionen,
die den Datensatz gelesen haben, werden invalidiert (`warm_up`-Properties danach proaktiv neu berechnet).

**Produktion:** Geteiltes Cache-Backend (Redis). Der Dependency-Index ist ab 0.52.0 geshardet
und die Invalidierung koordiniert; der Run-Cache-Speicher wird ab 0.69.x beschränkt/prozessweit
evakuiert (transparent für die Nutzung).

---

## 13) History, Audit & Temporale Abfragen (As-of)

### Audit Trail

GM integriert `django-simple-history`. Automatisch hinzugefügte Felder:

| Feld                    | Bedeutung                                |
| ----------------------- | ---------------------------------------- |
| `history_date`          | Zeitstempel der Änderung                 |
| `history_user_id`       | User-ID (aus `creator_id`)               |
| `history_change_reason` | Kommentar (aus `history_comment`)        |
| `history_type`          | `+` (create), `~` (update), `-` (delete) |

```python
projekt.history.all()
projekt.history.filter(history_change_reason__icontains="import")
projekt.history.order_by("-history_date").first()
```

### Temporale Abfragen (As-of, ab 0.7x)

Reads „wie zu einem bestimmten Zeitpunkt" — inkl. historischem M2M-Tracking. Zwei Wege:

**Python — Context-Manager `as_of`:**

```python
from general_manager import as_of, current_as_of_date

with as_of(datetime(2026, 1, 1)):
    stand = Projekt.all()                 # liefert den Stand zum Stichtag
    kennzahl = ProjektKennzahlen(projekt=p).summe_ist_kosten  # auch Berechnungen as-of
    # current_as_of_date() -> datetime(2026, 1, 1)
```

- Der Stichtag wird über ORM-Reads **und** Calculation-Queries propagiert.
- Verschachtelte `as_of` mit *abweichendem* Zeitpunkt → `HistoricalContextConflictError`.
- **Mutations in einem As-of-Kontext sind verboten** → `HistoricalMutationError`.

**GraphQL — `@asOf`-Directive (query-only):**

```graphql
query ($stichtag: DateTime!) @asOf(date: $stichtag) {
  projektList { items { id auftragsnummer offerteSumme { value unit } } }
}
```

- Genau **eine** `@asOf`-Directive pro Operation, nur auf Query-Operationen, Argument `date`.
- Auf Mutations/Subscriptions nicht erlaubt.

> Der ältere Weg `Projekt.filter(search_date=datetime(...))` existiert weiterhin für einfache
> Point-in-time-Filter; für ganze Read-Szenarien (mehrere Manager/Berechnungen konsistent zum
> selben Stichtag) ist der `as_of`-Kontext bzw. `@asOf` der robustere Weg.

---

## 14) Observability / Logging

```python
GENERAL_MANAGER = {
    "PERMISSION_AUDIT": True,
    # Logt: Akteur, Action-Typ, betroffene Attribute, Authorization-Outcome
    # Inkl. candidate/authorized/denied rows pro GraphQL-List-Query
}
LOGGING = {"loggers": {"general_manager": {"handlers": ["json_handler"], "level": "INFO"}}}
```

> **Ab 0.7x:** Mutation-Phasen-Latenzen werden als Observability-Signale attributiert
> (Data-Change-Transaction-Lifecycle) — nützlich, um teure Mutationen/Invalidierungen zu messen.

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
            filters = {"status": RequestFilter(remote_name="state", value_type=str)}
            query_operations = {
                "list":   RequestQueryOperation(method="GET", path="/projects"),
                "detail": RequestQueryOperation(method="GET", path="/projects/{id}"),
            }
            transport        = UrllibRequestTransport()
            transport_config = RequestTransportConfig(
                base_url="https://service.example.com/api", timeout=10)
            auth_provider    = BearerTokenAuthProvider(token=lambda: "token-here")
```

Nicht als generischen HTTP-Client verwenden — `RequestInterface` ist ressourcen-orientiert.

---

## 16) Workflow-Automation

```python
GENERAL_MANAGER = {
    "WORKFLOW_SIGNAL_BRIDGE": True,   # CRUD-Signale als Workflow-Events publizieren
    # "WORKFLOW_ENGINE": "LocalWorkflowEngine"  # oder CeleryWorkflowEngine
}
```

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

```bash
python manage.py workflow_drain_outbox          # ausstehende Events abarbeiten
python manage.py workflow_replay_dead_letters   # fehlgeschlagene nochmal versuchen
```

> **Verwandte periodische Commands (Celery Beat):** `search_reconcile` (Abschnitt 11),
> `graphql_warmup` / `graphql_warmup_refresh_due` (Abschnitt 12), `chat_cleanup` (Abschnitt 18).

---

## 17) File-Uploads

Ab 0.7x bringt GM eine **File-Upload-Pipeline** für Django `FileField`/`ImageField`, exponiert
über typisierte GraphQL-Felder. Modell: Der Client fordert eine **Upload-Intent** an (Token),
lädt die Datei hoch und die Datei wird **nach dem Commit finalisiert** — Permissions werden vor
dem Token geprüft (preflight).

```python
from general_manager import FileUploadPolicy   # top-level importierbar

class Interface(DatabaseInterface):
    dokument = models.FileField(upload_to="dokumente/")
    # Upload-Regeln über eine FileUploadPolicy (Größe, Typen, Sichtbarkeit, Inspektion)

policy = FileUploadPolicy(
    max_bytes=10 * 1024 * 1024,                     # optionales Größenlimit
    allowed_content_types=["application/pdf"],       # optionale MIME-Whitelist
    allowed_extensions=[".pdf"],                     # optionale Extension-Whitelist
    public=False,                                    # öffentlich zugreifbar?
    # content_inspector=<callable>                   # optionale Inhaltsprüfung
)
```

Relevante Bausteine (alle top-level aus `general_manager` importierbar):

- **Policy/Config:** `FileUploadPolicy`, `FileInspection`, `FileContentInspector`, `FileUploadConfigurationError`
- **GraphQL-Typen:** `UploadToken` (Intent/Token), `StoredFile`, `StoredImage` (typisierte Felder)
- **Adapter:** `register_upload_adapter`, `UploadAdapter`, `UploadFinalizationAdapter`,
  `ExactPublicDownloadAdapter`, `ProxyUploadSink`, `UploadInstructions`
- **Fehler:** `UploadError`, `UploadExpiredError`, `UploadTokenInvalidError`, `UploadIncompleteError`

Ablauf (vereinfacht): typisiertes GraphQL-Upload-Feld wird für das `FileField` generiert →
Client holt eine **feldgebundene, einmalig nutzbare** Upload-Intent (Token, Permission-Preflight)
→ Datei wird über den Transport/Adapter hochgeladen (auch Proxy-Streaming möglich) → nach
DB-Commit finalisiert; sichere Downloads über den Download-Adapter. Für den vollständigen Flow
inkl. Storage-Adapter siehe Upstream-Doku.

> Da dies mehrere bewegliche Teile hat (Storage-Adapter, Tokens, Finalisierung), vor
> Produktiv-Einsatz gegen die Upstream-Doku und die konkrete Storage-Backend-Konfiguration abgleichen.

---

## 18) Chat / NLI-Subsystem

Ab 0.7x enthält GM ein optionales **Chat-/Natural-Language-Interface-Subsystem** (Paket
`general_manager.chat`) mit Persistenz-Modellen (eigene Migrations) und Provider-Anbindung
(u. a. OpenAI). Zweck: natürlich-sprachliche Interaktion mit den GM-Daten, inkl.
Pending-Confirmation-Flow für Aktionen und einem Eval-Runner für Prompt-Zuverlässigkeit.

- Wird beim App-Start verdrahtet und über die Public-Exports zugänglich gemacht.
- Aufräum-Command: `python manage.py chat_cleanup`.

> **Scope-Hinweis:** Forge nutzt dieses Subsystem aktuell nicht. Es ist hier nur der
> Vollständigkeit halber erwähnt — für Details zur Konfiguration (Provider, Persistenz,
> Confirmation-Flow) die Upstream-Doku heranziehen, bevor man es aktiviert.

---

## 19) INSTALLED_APPS-Reihenfolge

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

GENERAL_MANAGER = {"AUTOCREATE_GRAPHQL": True, "GRAPHQL_URL": "graphql/"}
```

---

## 20) CSRF & Frontend-Anbindung

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

```typescript
// Apollo Client
const apolloClient = new ApolloClient({
  link: new HttpLink({ uri: "/graphql/" }),
  cache: new InMemoryCache(),
});
// Vite-Proxy
server: { proxy: { "/graphql": "http://localhost:8000" } }
```

---

## 21) Häufige Gotchas

| Problem                                                  | Ursache                                                           | Lösung                                                                                                   |
| -------------------------------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `/admin/` → `NoReverseMatch: app_list`                   | `general_manager` vor `django.contrib.admin`                      | Django-Builtins zuerst (Abschnitt 19)                                                                    |
| `GraphQLPropertyReturnAnnotationError`                   | `@graph_ql_property` ohne `-> Typ` (ab 0.68.0 Pflicht)            | Return-Annotation ergänzen; sie treibt den GraphQL-Ausgabetyp                                            |
| `Bitte höchstens 2 Dezimalstellen`                       | GM gibt `float` ans Model; `DecimalField` → IEEE-754-Präzision    | `full_clean()` in Interface überschreiben (siehe unten)                                                  |
| `super()` in Interface-Methode schlägt fehl             | GM kopiert Methoden als plain functions; `__class__`-Cell falsch  | MRO manuell durchlaufen (siehe Decimal-Float-Fix)                                                        |
| `Unknown type 'Decimal'`                                 | GM kennt keinen `Decimal`-Scalar                                  | `Float!` für DecimalField, `String!` für MeasurementField                                                |
| `Cannot query field 'projekt'` auf Mutation              | Rückgabefeld = Klassenname (Grossbuchstabe)                       | `Projekt { ... }` statt `projekt { ... }`                                                                |
| `projektList` statt `projekt_list`                       | GM erzeugt camelCase                                              | Immer camelCase in GraphQL-Queries                                                                       |
| Mehrwort-Klasse → falsch geschriebenes Root-Feld         | Vor 0.42.1 kleingeschrieben                                       | camelCase: `IstWert` → `istWertList`                                                                     |
| `items` statt `results` in Paginierung                   | GM nennt das Feld `items`                                         | `{ items { ... } pageInfo { totalCount } }`                                                              |
| `projektleiter { username }` schlägt fehl                | ForeignKey → `String` in GraphQL                                  | Kein Sub-Selection; direkt als String abfragen                                                           |
| CalculationInterface-Liste zeigt alle Daten              | `possible_values` gibt list() statt Bucket                       | `possible_values=lambda: Manager.all()` — Bucket, kein `list(...)`                                       |
| `Input.monthly_date(year=...)` → `TypeError`             | Helfer nehmen `start`/`end` (date)                               | `Input.monthly_date(start=date(...), end=date(...))` (keyword-only)                                      |
| `@cached(scope="run")` → `TypeError`                     | Keyword heißt seit 0.50.0 `cache=`                               | `@cached(cache="run")`                                                                                   |
| `@cached(timeout=N)` → `CacheTimeoutConfigurationError`  | `timeout` nur mit `cache="timeout"` erlaubt                      | `@cached(cache="timeout", timeout=N)`                                                                    |
| `scoped_cache` nicht importierbar                        | Es gibt kein `scoped_cache`                                       | `@cached(cache="run")`                                                                                   |
| `warm_up=True requires cache=...`                        | `warm_up` braucht `dependency` oder `timeout`                     | `@graph_ql_property(cache="dependency", warm_up=True)`                                                   |
| `HistoricalMutationError`                                | create/update/delete innerhalb `with as_of(...)` / `@asOf`        | Mutationen außerhalb des As-of-Kontexts ausführen (As-of ist read-only)                                  |
| `HistoricalContextConflictError`                         | verschachtelte `as_of` mit abweichendem Stichtag                 | Nur einen Stichtag pro Read-Szenario verwenden                                                           |
| Property/Hilfsmethode wird mehrfach berechnet            | Private Methoden werden nicht vom run-cache erfasst              | Abgeleitete `@graph_ql_property` andere Properties lesen lassen, `@cached(cache="run")` auf Helfer, oder `bucket.index_by()` |
| `Measurement("50 cm")` liefert nicht das Erwartete       | Einzel-String → `from_string`                                    | `Measurement.from_string("50 cm")` bzw. `Measurement(50, "cm")`                                          |
| `to_dataframe` wirft `ModuleNotFoundError`               | `pandas` ist optionale Dependency, nicht installiert            | `pandas` installieren (bzw. als Extra), dann DataFrame-Helfer nutzen                                     |
| Suche aktualisiert sich nicht nach Datenänderung         | Auto-Reindex in 0.55.0 entfernt; Index nur "dirty"              | `search_reconcile` laufen lassen (`--once` oder Celery Beat)                                             |
| `cache="auto"` Fehler                                    | Modus in 0.42.0 entfernt                                         | `cache="run"` (Default) oder `cache="dependency"`                                                        |
| `Float cannot represent non numeric value`               | Frontend schickt String statt Zahl                              | `parseFloat(val.replace(",", "."))`                                                                      |
| Vite zeigt nichts im Container                           | Vite lauscht nur auf localhost                                  | `npm run dev -- --host`                                                                                  |

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

## 22) Weiterführende Upstream-Doku

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