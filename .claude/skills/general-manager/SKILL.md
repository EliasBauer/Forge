---
name: general-manager
description: Verifizierte Patterns, Konventionen und API des GeneralManager-Frameworks (GM, v0.56.0) für das Forge-Backend. Nutze diese Skill IMMER bei Backend-Arbeit in Forge — beim Definieren oder Ändern von Manager-Klassen, Interfaces (Database/Existing/ReadOnly/Calculation/Request), Buckets/Filtern, Permissions (ABAC), Rules, Factories/Seeding, MeasurementField, der GraphQL-Autogenerierung, Subscriptions, Caching/Warm-up, Search oder Workflow-Automation — auch wenn der Begriff "GeneralManager" nicht ausdrücklich fällt. Die GM-API weicht an vielen Stellen von Standard-Django ab; verlasse dich auf diese geprüfte Referenz statt auf Annahmen.
---

# GeneralManager (GM) — Forge Backend

Geprüfte Referenz für das GM-Framework (v0.56.0, gegen Quellcode verifiziert), so wie Forge es nutzt.

## Goldene Regel: keine GM-API erfinden

GM weicht oft von Standard-Django ab, und geratene API ist hier schon mehrfach falsch gewesen. Bevor du GM-Code schreibst, **lies den passenden Abschnitt in `references/reference.md`**. Bist du dir bei einer Signatur, einem Decorator-Keyword oder einem Command-Namen unsicher: nachschlagen, nicht raten. Die Referenz hat ein Inhaltsverzeichnis mit 20 nummerierten Abschnitten.

## Architektur in einem Satz

GM legt über Django vier Komponenten: **Manager** (leichter Wrapper, Typ-Hints + CRUD), **Interface** (Persistenz-Strategie: Database / Existing / ReadOnly / Calculation / Request), **Bucket** (typisierte, lazy Collection wie ein Queryset), **Dependency Tracker** (mappt Attributzugriffe auf Cache-Keys, invalidiert automatisch).

## Immer geltende Guardrails

Diese Fehler sind häufig und teuer — halte sie ohne Nachschlagen ein:

- **Feldzugriff** immer via `self.feldname` — nie via `self._interface._instance`.
- **Typ-Annotationen auf die Manager-Klasse** (echte Python-Typen), **nur Model-Field-Definitionen ins `Interface(DatabaseInterface)`**.
- **`possible_values` muss einen Bucket liefern**, keine Liste: `possible_values=lambda: Projekt.all()` — nicht `list(...)`. Eine Liste kann nicht per `.filter(id=...)` eingegrenzt werden, sonst liefert die Query alle Werte.
- **Jeder `CalculationInterface`-Manager braucht `CalculationPermission`** (Forge-Pattern, §5) — sonst `Unknown input field 'id' in filter` bei List-Queries normaler Nutzer.
- **`INSTALLED_APPS`: `django.contrib.admin` vor `general_manager`** (§17) — sonst `NoReverseMatch: app_list` auf `/admin/`.
- **Related-Lookups über den GM**, nicht raw ORM: `KostenPosition.filter(projekt=self.projekt)`.

## GraphQL-Konventionen (Autogen)

- Felder/Queries sind **camelCase**: `IstWert` → `istWert` / `istWertList` (ab 0.42.1, auch Mehrwort-Klassen).
- **ForeignKey → `String`** (str() des Objekts), keine Sub-Selection.
- **Mutation-Rückgabefeld = Klassenname mit Großbuchstabe**: `createProjekt { ... Projekt { id } }`.
- Listen: `{ items { ... } pageInfo { totalCount } }` (nicht `results`).
- `MeasurementField` → `MeasurementType { value unit }`; Mutation-Input als String `"50000 CHF"`.

## Caching-Kurzregeln

- Default-Modus ist `run` (der frühere `auto`-Modus existiert seit 0.42.0 nicht mehr).
- `@graph_ql_property` und `@cached` nutzen seit 0.50.0 dasselbe Keyword `cache=` (nicht `scope=`). Modi: `run | dependency | timeout | none`.
- `timeout=N` **nur** mit `cache="timeout"`. `warm_up=True` braucht `cache="dependency"` oder `"timeout"`.

## Measurement

- Kombinierte „Wert+Einheit"-Strings: `Measurement.from_string("50 cm")`. Getrennt: `Measurement(50, "cm")`.

## Wann welchen Referenz-Abschnitt lesen

`references/reference.md` (verifiziert, v0.56.0):

- Manager / Interfaces definieren → §2
- CRUD, `get`-Shortcut, Soft-Delete → §3
- Buckets, Filter, `index_by` / `index_many`, Dependency-Semantik → §4
- Permissions (ABAC), `__based_on__`, CalculationPermission → §5
- Rules / Validators → §6 · Factories / Seeding (`seed_manager_landscape`) → §7
- MeasurementField → §8 · GraphQL (Queries / Mutations / Relation-Filter) → §9 · Subscriptions → §10
- Search (+ `search_reconcile`, ab 0.55.0) → §11 · Caching & Warm-up → §12
- History / Audit → §13 · Observability → §14 · RequestInterface → §15 · Workflow → §16
- INSTALLED_APPS-Reihenfolge → §17 · CSRF / Frontend → §18 · **Gotchas-Tabelle → §19**

Bei einem konkreten Fehler zuerst die Gotchas-Tabelle (§19) — sie mappt Symptom → Ursache → Lösung.