# Todo: Aufgaben – App + Onboarding-Hilfestellung

Spec: `specs/aufgaben.md`

## Backend

- [x] 1. Berechnungs-GMs aufgeteilt:
  - `apps/stunden/calculation_manager/aufgaben_stundensatz.py` → `AufgabenStundensatz`
  - `apps/calculation_manager/ist_werte.py` → `IstWert`
  - In `INSTALLED_APPS` in `forge/settings.py` eingetragen

- [x] 2. `AufgabenStundensatz`-GM implementiert
  - `CalculationInterface` ohne Input-Felder
  - `@graph_ql_property fehlende_stundensatz_jahre() -> list[int]`

## Frontend

- [x] 3. Nav-Reihenfolge anpassen (`Layout.tsx`)
  - Aufgaben (→ `/aufgaben`) als erster Link
  - dann Projekte, dann Stundensätze

- [x] 4. Route `/aufgaben` in `App.tsx` eintragen
  - Nur authentifizierte User (kein `allowedGroups`-Filter)
  - Standardroute `/` auf `/aufgaben` umbiegen

- [x] 5. GraphQL-Query in `queries.ts` hinzufügen
  - `GET_FEHLENDE_STUNDENSATZ_JAHRE` (fehlende_stundensatz_jahre)

- [x] 6. `AufgabenPage.tsx` erstellen
  - Sektion „Stundensatz": Liste der fehlenden Jahre
  - Leerzustand: „Alles vollständig" wenn nichts fehlt
