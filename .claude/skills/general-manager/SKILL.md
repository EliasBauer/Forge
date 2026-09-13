---
name: general-manager
description: Verifizierte Patterns, Konventionen und API des GeneralManager-Frameworks (GM, v0.80.4) für das Forge-Backend. Nutze diese Skill IMMER bei Backend-Arbeit in Forge — beim Definieren oder Ändern von Manager-Klassen, Interfaces (Database/Existing/ReadOnly/Calculation/Request/Excel), Buckets/Filtern/Projektionen, Permissions (ABAC), Rules, Factories/Seeding, MeasurementField/DataFrames, der GraphQL-Autogenerierung, Subscriptions, Caching/Warm-up, Search, temporalen (As-of-)Abfragen, File-Uploads, dem Excel-Interface oder Workflow-Automation — auch wenn der Begriff "GeneralManager" nicht ausdrücklich fällt. Die GM-API weicht an vielen Stellen von Standard-Django ab; verlasse dich auf diese geprüfte Referenz statt auf Annahmen.
---

# GeneralManager (GM) — Forge Backend

Geprüfte Referenz für das GM-Framework (v0.80.4, gegen Quellcode verifiziert), so wie Forge es nutzt.

## Goldene Regel: keine GM-API erfinden

GM weicht oft von Standard-Django ab, und geratene API ist hier schon mehrfach falsch gewesen. Bevor du GM-Code schreibst, **lies den passenden Abschnitt in `references/reference.md`**. Bist du dir bei einer Signatur, einem Decorator-Keyword oder einem Command-Namen unsicher: nachschlagen, nicht raten. Die Referenz hat ein Inhaltsverzeichnis mit 23 nummerierten Abschnitten (Excel-Interface = §16, jüngster Zugang ab 0.78.0).

## Architektur in einem Satz

GM legt über Django vier Komponenten: **Manager** (leichter Wrapper, Typ-Hints + CRUD), **Interface** (Persistenz-Strategie: Database / Existing / ReadOnly / Calculation / Request / **Excel**), **Bucket** (typisierte, lazy Collection wie ein Queryset), **Dependency Tracker** (mappt Attributzugriffe auf Cache-Keys, invalidiert automatisch).

## Immer geltende Guardrails

Diese Fehler sind häufig und teuer — halte sie ohne Nachschlagen ein:

- **Feldzugriff** immer via `self.feldname` — nie via `self._interface._instance`.
- **Typ-Annotationen auf die Manager-Klasse** (echte Python-Typen), **nur Model-Field-Definitionen ins `Interface(DatabaseInterface)`**.
- **`@graph_ql_property` braucht eine Return-Annotation** (`-> Typ`, ab 0.68.0 Pflicht) — sie treibt den GraphQL-Ausgabetyp; ohne sie: `GraphQLPropertyReturnAnnotationError`.
- **`possible_values` muss einen Bucket liefern**, keine Liste: `possible_values=lambda: Projekt.all()` — nicht `list(...)`. Eine Liste kann nicht per `.filter(id=...)` eingegrenzt werden, sonst liefert die Query alle Werte.
- **Jeder `CalculationInterface`-Manager braucht `CalculationPermission`** (Forge-Pattern, §5) — sonst `Unknown input field 'id' in filter` bei List-Queries normaler Nutzer.
- **`INSTALLED_APPS`: `django.contrib.admin` vor `general_manager`** (§20) — sonst `NoReverseMatch: app_list` auf `/admin/`.
- **Related-Lookups über den GM**, nicht raw ORM: `KostenPosition.filter(projekt=self.projekt)`. Für wiederholte Lookups in Berechnungen `bucket.index_by()` / `index_many()` (§4).

## GraphQL-Konventionen (Autogen)

- Felder/Queries sind **camelCase**: `IstWert` → `istWert` / `istWertList` (ab 0.42.1, auch Mehrwort-Klassen).
- **ForeignKey → `String`** (str() des Objekts), keine Sub-Selection.
- **Mutation-Rückgabefeld = Klassenname mit Großbuchstabe**: `createProjekt { ... Projekt { id } }`.
- Listen: `{ items { ... } pageInfo { totalCount } }` (nicht `results`).
- `MeasurementField` → `MeasurementType { value unit }`; Mutation-Input als String `"50000 CHF"`.
- Strukturierte Property-Rückgaben werden zu GraphQL-Objekttypen (ab 0.68.0); Fehler kommen als strukturierter `PublicGraphQLError`-Contract.
- **Group-Sums über Text-Felder aggregieren die Werte jetzt *unique*** (ab 0.79.2) — bei Aggregationen also nicht mit Duplikaten rechnen.
- **Update-Mutations sind partiell** (ab 0.80.1): weggelassene Argumente/`undefined` lassen den gespeicherten Wert stehen, **nur explizites `null` leert** ein Feld. Frontend-Formulare für optionale Felder senden `null`, nicht `undefined` (§9).
- **Subscriptions dürfen lazy Relationen im `item`-Selection-Set abfragen** (ab 0.79.5, Wert-Auflösung läuft off-event-loop). `select_related` bleibt für N+1 sinnvoll, ist aber kein Crash-Schutz mehr (§10).
- **No-op-Updates schreiben nichts** (ab 0.79.6): kein `save()`, keine History-Zeile — Tests, die History zählen, brauchen eine echte Änderung oder `history_comment` (§13).

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

- Uploads für Django `FileField`/`ImageField` über `FileUploadPolicy` + typisierte GraphQL-Felder (`UploadToken`, `StoredFile`/`StoredImage`); Flow: Intent/Token → Upload → Finalisierung nach Commit (§18). Vor Produktiv-Einsatz gegen Upstream + Storage-Backend abgleichen.

## Excel-Interface (neu ab 0.78.0, öffentliche API ab 0.79.0)

- Neuer Interface-Typ neben Database/…: **`ExcelInterface`** bindet einen Manager an eine Excel-Arbeitsmappe mit gemeinsam genutztem, cache-gestütztem In-Memory-Mirror. Import: `from general_manager import ExcelInterface, ExcelField, ExcelCharField, ExcelIntegerField, ExcelDecimalField`.
- Konfiguration über innere `Meta` (→ `ExcelMeta`): `workbook` (Pfad, Pflicht) · `sheet` · `key` (muss eine deklarierte ExcelField benennen) · **genau eines** von `table` ODER `header_row` (`header_row >= 1`) · optional `cache_alias="default"`, `cache_version="1"`.
- Felder: `ExcelField(python_type, required=True, default=None, header=None, aliases=(), unique=False, editable=True, parser=None, dumper=None)` oder typisiert `ExcelCharField(max_length=…)`, `ExcelIntegerField`, `ExcelDecimalField(max_digits=…, decimal_places=…)`.
- Abfrage (Classmethods): `filter(**kwargs)` / `exclude(**kwargs)` / `all()` → Bucket (`ExcelBucket`); `sync_from_excel(force=False)` → `ExcelSyncDelta(created, updated, deleted)`.
- FRISCH (ab 0.78.0) — vor Produktiv-Einsatz gegen Upstream abgleichen. Vollständige Details/Feld-Optionen → §16 der `reference.md`.

## Wann welchen Referenz-Abschnitt lesen

`references/reference.md` (verifiziert, v0.80.4):

- Manager / Interfaces / `@graph_ql_property` (Return-Annotation!) / ReadOnly-Startup-Sync (`READ_ONLY_SYNC_ON_STARTUP`, ab 0.80.0) → §2
- CRUD, `get`-Shortcut, Soft-Delete → §3
- Buckets, Filter, `values()`/`values_list()`, `index_by`/`index_many`, Relation-Sortierung, Dependency-Semantik → §4
- Permissions (ABAC), `__based_on__`, CalculationPermission → §5
- Rules / Validators (dotted Placeholders) → §6 · Factories / Seeding (`seed_manager_landscape`) → §7
- MeasurementField + DataFrame-Export (`to_dataframe`/`from_dataframe`) → §8
- GraphQL (Queries / **partielle Update-Mutations ab 0.80.1** / Relation-Filter / Output-Typen / Fehler-Contract / unique Text-Group-Sums) → §9 · Subscriptions (off-event-loop ab 0.79.5) → §10
- Search (+ `search_reconcile`, Invalidierungs-Regeln, Meilisearch `task_timeout_in_ms`) → §11 · Caching & Warm-up → §12
- History / Audit (No-op-Updates ohne History ab 0.79.6) **& Temporale (As-of-) Abfragen** → §13 · Observability → §14 · RequestInterface → §15
- **Excel-Interface** (`Meta`/`ExcelField`/`sync_from_excel`, ab 0.78.0) → §16 · Workflow → §17
- **File-Uploads → §18** · **Chat / NLI-Subsystem → §19** (API weiterhin *planned*/instabil — 0.77–0.79.1 brachten nur Hardening, keine stabile öffentliche API)
- INSTALLED_APPS-Reihenfolge → §20 · CSRF / Frontend → §21 · **Gotchas-Tabelle → §22** · Upstream-Doku → §23

Bei einem konkreten Fehler zuerst die Gotchas-Tabelle (§22) — sie mappt Symptom → Ursache → Lösung.