# Todo: GM 0.56.0 – Calculation-Manager-Optimierung

Hintergrund: GM-Update 0.45.0 → 0.56.0. Neue Run-Cache-APIs ermöglichen,
wiederholte Filter-Lookups in den Calculation-Managern idiomatisch zu lösen.
ACHTUG!!! Benutzte den aktualisierten SKILL für dieses TODO!!!
/workspaces/Forge/docs/skills/backend-design/SKILL.md

## Problem

`ProjektKennzahlen`: Die drei privaten Hilfsmethoden `_summe_ist()`,
`_summe_offerte()`, `_summe_wv()` sind keine `@graph_ql_property` und daher
nicht run-gecacht. Pro GraphQL-Auflösung werden sie bis zu 5×, 3×, 4× neu
berechnet (inkl. DB-Query).

`IstWert`: `Lieferantenrechnung.filter(richtiger_titel=...)` wird in
`ist_kosten_wert` und `ist_kosten_wert_prozent` separat aufgerufen. Über
mehrere `IstWert`-Instanzen (eine pro Kostenart) für dasselbe Projekt
entsteht so pro Kostenart ein weiterer Lookup.

## Backend

- [x] 1. `ProjektKennzahlen` – Hilfsmethoden run-cachen
  - Datei: `src/apps/projekt/calculation_manager/projekt_kennzahlen.py`
  - Import ergänzen: `from general_manager.cache.cache_decorator import cached`
  - `@cached` auf `_summe_ist`, `_summe_offerte`, `_summe_wv` setzen
  - Damit werden Mehrfachaufrufe derselben Hilfsmethode im selben Run gecacht

- [x] 2. `IstWert` – gecachte Hilfsmethode für Lieferantenrechnungs-Lookups
  - Datei: `src/apps/projekt/calculation_manager/ist_wert.py`
  - Import ergänzen: `from general_manager.cache.cache_decorator import cached`
  - Hilfsmethode `_rechnungen_nach_konto()` mit `@cached` hinzufügen:
    - gibt `Lieferantenrechnung.filter(richtiger_titel=self.projekt.auftragsnummer).index_many("buchungskonto__account_no")` zurück
    - Typ: `dict[str | None, tuple[Lieferantenrechnung, ...]]`
  - `ist_kosten_wert` umbauen: statt `filter(buchungskonto__account_no=...)` →
    `_rechnungen_nach_konto().get(str(konto_nr), ())`
  - "diverses"-Zweig: statt Python-Liste-Comprehension →
    bekannte Konto-Nummern als `frozenset` bilden, dann über Index iterieren
  - `ist_kosten_wert_prozent` umbauen: statt erneutem `filter(...)` →
    alle Werte aus `_rechnungen_nach_konto()` flatten

## Verifikation

- `python -m pytest -x -q` → alle Tests grün, Coverage 100%
- Manuell in ipython prüfen: `ProjektKennzahlen(projekt=p).summe_ist_kosten`
  und `IstWert(projekt=p, kostenart=k).ist_kosten_wert` lösen korrekt auf
