---
name: general-manager
description: Verifizierte Patterns, Konventionen und API des GeneralManager-Frameworks (GM, v0.76.0) für das Forge-Backend. Nutze diese Skill IMMER bei Backend-Arbeit in Forge — beim Definieren oder Ändern von Manager-Klassen, Interfaces (Database/Existing/ReadOnly/Calculation/Request), Buckets/Filtern/Projektionen, Permissions (ABAC), Rules, Factories/Seeding, MeasurementField/DataFrames, der GraphQL-Autogenerierung, Subscriptions, Caching/Warm-up, Search, temporalen (As-of-)Abfragen, File-Uploads oder Workflow-Automation — auch wenn der Begriff "GeneralManager" nicht ausdrücklich fällt. Die GM-API weicht an vielen Stellen von Standard-Django ab; verlasse dich auf diese geprüfte Referenz statt auf Annahmen.
---

# GeneralManager (GM) — Forge Backend

Geprüfte Referenz für das GM-Framework (v0.76.0, gegen Quellcode verifiziert), so wie Forge es nutzt.

## Goldene Regel: keine GM-API erfinden

GM weicht oft von Standard-Django ab, und geratene API ist hier schon mehrfach falsch gewesen. Bevor du GM-Code schreibst, **lies den passenden Abschnitt in `references/reference.md`**. Bist du dir bei einer Signatur, einem Decorator-Keyword oder einem Command-Namen unsicher: nachschlagen, nicht raten. Die Referenz hat ein Inhaltsverzeichnis mit 22 nummerierten Abschnitten.

## Architektur in einem Satz

GM legt über Django vier Komponenten: **Manager** (leichter Wrapper, Typ-Hints + CRUD), **Interface** (Persistenz-Strategie: Database / Existing / ReadOnly / Calculation / Request), **Bucket** (typisierte, lazy Collection wie ein Queryset), **Dependency Tracker** (mappt Attributzugriffe auf Cache-Keys, invalidiert automatisch).

## Immer geltende Guardrails

Diese Fehler sind häufig und teuer — halte sie ohne Nachschlagen ein:

- **Feldzugriff** immer via `self.feldname` — nie via `self._interface._instance`.
- **Typ-Annotationen auf die Manager-Klasse** (echte Python-Typen), **nur Model-Field-Definitionen ins `Interface(DatabaseInterface)`**.
- **`@graph_ql_property` braucht eine Return-Annotation** (`-> Typ`, ab 0.68.0 Pflicht) — sie treibt den GraphQL-Ausgabetyp; ohne sie: `GraphQLPropertyReturnAnnotationError`.
- **`possible_values` muss einen Bucket liefern**, keine Liste: `possible_values=lambda: Projekt.all()` — nicht `list(...)`. Eine Liste kann nicht per `.filter(id=...)` eingegrenzt werden, sonst liefert die Query alle Werte.
- **Jeder `CalculationInterface`-Manager braucht `CalculationPermission`** (Forge-Pattern, §5) — sonst `Unknown input field 'id' in filter` bei List-Queries normaler Nutzer.
- **`INSTALLED_APPS`: `django.contrib.admin` vor `general_manager`** (§19) — sonst `NoReverseMatch: app_list` auf `/admin/`.
- **Related-Lookups über den GM**, nicht raw ORM: `KostenPosition.filter(projekt=self.projekt)`. Für wiederholte Lookups in Berechnungen `bucket.index_by()` / `index_many()` (§4).

## GraphQL-Konventionen (Autogen)

- Felder/Queries sind **camelCase**: `IstWert` → `istWert` / `istWertList` (ab 0.42.1, auch Mehrwort-Klassen).
- **ForeignKey → `String`** (str() des Objekts), keine Sub-Selection.
- **Mutation-Rückgabefeld = Klassenname mit Großbuchstabe**: `createProjekt { ... Projekt { id } }`.
- Listen: `{ items { ... } pageInfo { totalCount } }` (nicht `results`).
- `MeasurementField` → `MeasurementType { value unit }`; Mutation-Input als String `"50000 CHF"`.
- Strukturierte Property-Rückgaben werden zu GraphQL-Objekttypen (ab 0.68.0); Fehler kommen als strukturierter `PublicGraphQLError`-Contract.

## Caching-Kurzregeln

- Default-Modus ist `run` (der frühere `auto`-Modus existiert seit 0.42.0 nicht mehr).
- `@graph_ql_property` und `@cached` nutzen seit 0.50.0 dasselbe Keyword `cache=` (nicht `scope=`); bare `@cached` funktioniert. Modi: `run | dependency | timeout | none`.
- `timeout=N` **nur** mit `cache="timeout"`. `warm_up=True` braucht `cache="dependency"` oder `"timeout"` (proaktiver Warm-up, §12).

## Measurement & DataFrames

- Kombinierte „Wert+Einheit"-Strings: `Measurement.from_string("50 cm")`. Getrennt: `Measurement(50, "cm")`.
- GM-Daten → pandas: `to_dataframe(rows, measurement_fields=[...])` / zurück `from_dataframe(...)` (pandas ist optionale Dependency, §8). Kombiniert gut mit Bucket-Projektionen `values()` / `values_list()` (§4).

## Temporale (As-of-) Abfragen & Mutations-Verbot

- Point-in-time-Reads: Python `with as_of(datetime(...)):` oder GraphQL `@asOf(date:)` (query-only, §13).
- **Mutations im As-of-Kontext sind verboten** → `HistoricalMutationError`. As-of ist read-only.

## File-Uploads (ab 0.7x)

- Uploads für Django `FileField`/`ImageField` über `FileUploadPolicy` + typisierte GraphQL-Felder (`UploadToken`, `StoredFile`/`StoredImage`); Flow: Intent/Token → Upload → Finalisierung nach Commit (§17). Vor Produktiv-Einsatz gegen Upstream + Storage-Backend abgleichen.

## Wann welchen Referenz-Abschnitt lesen

`references/reference.md` (verifiziert, v0.76.0):

- Manager / Interfaces / `@graph_ql_property` (Return-Annotation!) → §2
- CRUD, `get`-Shortcut, Soft-Delete → §3
- Buckets, Filter, `values()`/`values_list()`, `index_by`/`index_many`, Relation-Sortierung, Dependency-Semantik → §4
- Permissions (ABAC), `__based_on__`, CalculationPermission → §5
- Rules / Validators (dotted Placeholders) → §6 · Factories / Seeding (`seed_manager_landscape`) → §7
- MeasurementField + DataFrame-Export (`to_dataframe`/`from_dataframe`) → §8
- GraphQL (Queries / Mutations / Relation-Filter / Output-Typen / Fehler-Contract) → §9 · Subscriptions → §10
- Search (+ `search_reconcile`, Invalidierungs-Regeln, ab 0.55.0) → §11 · Caching & Warm-up → §12
- History / Audit **& Temporale (As-of-) Abfragen** → §13 · Observability → §14 · RequestInterface → §15 · Workflow → §16
- **File-Uploads → §17** · **Chat / NLI-Subsystem → §18**
- INSTALLED_APPS-Reihenfolge → §19 · CSRF / Frontend → §20 · **Gotchas-Tabelle → §21** · Upstream-Doku → §22

Bei einem konkreten Fehler zuerst die Gotchas-Tabelle (§21) — sie mappt Symptom → Ursache → Lösung.