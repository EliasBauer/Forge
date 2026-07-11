# Spec: ProjektKennzahlen CalculationInterface

## Kontext

Die entfernten `@graph_ql_property`-Felder auf `Projekt` (`ist_koste`, `bisher_verrechnet`,
`summe_wv_plus`) und die aktuell im Frontend berechneten Aggregationen (Summen, Deltas,
Verbrauchsrate) gehören in ein `CalculationInterface` — nach dem Muster von `ist_werte.py`.

Zusätzlich ist `IstWert.ist_kosten_wert_prozent` aktuell broken, weil es
`self.projekt.ist_koste` referenziert, das nicht mehr existiert.

## Klärung: `summe_ist_kosten`

`summe_ist_kosten` = Summe **aller** Bexio-Lieferantenrechnungen für das Projekt
(`betrag − steuer_berechnet`, gefiltert auf `richtiger_titel = auftragsnummer`).

Rechnungen deren `buchungskonto__account_no` keiner bekannten `Kostenart.konto_nummer`
zugeordnet werden kann, laufen auf **"Diverses"**.
Damit gilt: Summe aller `IstWert.ist_kosten_wert` == `summe_ist_kosten`.

---

## 1. Neues CI: `ProjektKennzahlen`

**Datei:** `apps/bexio/calculation_manager/projekt_kennzahlen.py`

### Interface

```python
class Interface(CalculationInterface):
    projekt = Input(Projekt, possible_values=lambda: Projekt.all())
```

### Properties

| Property | Typ | Beschreibung |
|---|---|---|
| `summe_ist_kosten` | `Decimal` | Summe aller Lieferantenrechnungen (`betrag − steuer_berechnet`) für `projekt.auftragsnummer` |
| `summe_wv_plus` | `Decimal` | Ersetzt entferntes `Projekt.summe_wv_plus` — vorerst `wv_summe.magnitude` (Phase-2-TODO) |
| `bisher_verrechnet` | `Decimal` | `ist_erloese − summe_ist_kosten` (ist_erloese = 0 bis Phase 2) |
| `summe_offerte_kosten` | `Decimal` | Summe `KostenPosition.offerte_kosten_wert` (exkl. Ertragsblock + Stunden) |
| `summe_wv_kosten` | `Decimal` | Summe `KostenPosition.wv_kosten_wert` (exkl. Ertragsblock + Stunden) |
| `verbrauchsrate` | `Decimal \| None` | `summe_ist_kosten / summe_offerte_kosten × 100`, None wenn Basis 0 |
| `delta_wv_off` | `Decimal \| None` | `summe_wv_kosten − summe_offerte_kosten`, None wenn Basis 0 |
| `delta_wv_off_pct` | `Decimal \| None` | `delta_wv_off / summe_offerte_kosten × 100` |
| `delta_ist_plan` | `Decimal \| None` | `summe_ist_kosten − summe_wv_kosten`, None wenn Basis 0 |
| `delta_ist_plan_pct` | `Decimal \| None` | `delta_ist_plan / summe_wv_kosten × 100` |

Alle Decimal-Werte auf 2 Nachkommastellen (`quantize(Decimal("0.01"))`).

---

## 2. Änderung: `ist_werte.py`

### `ist_kosten_wert` — "Diverses" erhält Sammelposition

Aktuell: Kostenarten ohne `konto_nummer` (z.B. `diverses`) geben `None` zurück.

**Neu:** Für `schluessel == "diverses"`:
- Alle bekannten `konto_nummern` aus `Kostenart.all()` (nur nicht-None Werte) ermitteln
- Rechnungen summieren deren `buchungskonto__account_no` **nicht** in dieser Menge ist

```python
if self.kostenart.schluessel == "diverses":
    known_konten = {
        str(k.konto_nummer)
        for k in Kostenart.all()
        if k.konto_nummer is not None
    }
    rechnungen = Lieferantenrechnung.filter(richtiger_titel=self.projekt.auftragsnummer)
    rest = [r for r in rechnungen if r.buchungskonto.account_no not in known_konten]
    if not rest:
        return None
    summe = sum((r.betrag - r.steuer_berechnet for r in rest), Decimal("0"))
    return Measurement(summe, "CHF")
```

### `ist_kosten_wert_prozent` — Fix broken reference

Ersetzt `self.projekt.ist_koste` durch inline-Summe aller Rechnungen:

```python
rechnungen = list(Lieferantenrechnung.filter(richtiger_titel=self.projekt.auftragsnummer))
summe_ist = sum((r.betrag - r.steuer_berechnet for r in rechnungen), Decimal("0"))
if not summe_ist:
    return None
return Decimal(ist.magnitude / summe_ist * 100).quantize(Decimal("0.01"))
```

> Hinweis: Die Summe aller Rechnungen wird damit zweimal berechnet (hier und in
> `ProjektKennzahlen.summe_ist_kosten`). Kein zirkulärer Import möglich
> (`IstWert` ↔ `ProjektKennzahlen` beide in `bexio/calculation_manager/`).
> Refactor zu Hilfsfunktion ist möglich, aber außerhalb des Scope dieses Specs.

---

## 3. Backend `__init__.py`

`apps/bexio/calculation_manager/__init__.py` muss `ProjektKennzahlen` exportieren.

---

## 4. Frontend: GraphQL Queries (`queries.ts`)

### GET_PROJEKT

```graphql
projekt(id: $id) {
  ...
  projektKennzahlenList {
    items {
      summeOfferteKosten
      summeWvKosten
      summeIstKosten
      verbrauchsrate
      deltaWvOff
      deltaWvOffPct
      deltaIstPlan
      deltaIstPlanPct
      summeWvPlus
      bisherVerrechnet
    }
  }
}
```

### GET_PROJEKTE

```graphql
projektList {
  items {
    ...
    projektKennzahlenList {
      items {
        summeWvPlus
        summeIstKosten
      }
    }
  }
}
```

---

## 5. Frontend: ProjektDetailPage

Folgende Frontend-Berechnungen entfernen, durch `kennzahlen`-Objekt ersetzen
(`kennzahlen = p.projektKennzahlenList.items[0] ?? null`):

| Vorher (Frontend) | Nachher (Backend) |
|---|---|
| `summeOfferteKosten` (reduce) | `kennzahlen.summeOfferteKosten` |
| `summeWvKosten` (reduce) | `kennzahlen.summeWvKosten` |
| `summeIstKosten` (reduce) | `kennzahlen.summeIstKosten` |
| `verbrauchsrate` | `kennzahlen.verbrauchsrate` |
| `deltaWvOff` / `deltaWvOffPct` | `kennzahlen.deltaWvOff` / `kennzahlen.deltaWvOffPct` |
| `deltaIstPlan` / `deltaIstPlanPct` | `kennzahlen.deltaIstPlan` / `kennzahlen.deltaIstPlanPct` |
| `p.bisherVerrechnet` | `kennzahlen.bisherVerrechnet` |

`deltaPlanWv` / `deltaPlanWvPct` bleiben `0` (Plan-WV = WV bis Backend bereit).

---

## 6. Frontend: ProjektListePage

```ts
const kennzahlen = p.projektKennzahlenList.items[0];
// statt p.summeWvPlus → kennzahlen?.summeWvPlus
// statt p.istKoste   → kennzahlen?.summeIstKosten
```

TypeScript-Typen entsprechend anpassen.

---

## Tests

- Unit-Tests für alle Properties in `ProjektKennzahlen`
- Test: `summe_offerte_kosten` schließt Ertragsblock und Stunden aus
- Test: `summe_ist_kosten` summiert alle Rechnungen (auch nicht-kategorisierte)
- Test: `IstWert.ist_kosten_wert` für `diverses` enthält nicht-zugeordnete Rechnungen
- Test: `IstWert.ist_kosten_wert_prozent` funktioniert ohne `projekt.ist_koste`
- Orientierung: `docs/skills/testing/SKILL.md`

## Akzeptanzkriterien

- [ ] `ProjektKennzahlen` CI existiert und ist via GraphQL abfragbar
- [ ] `ist_werte.py` kompiliert ohne Fehler, `diverses` erhält Sammelposition
- [ ] Frontend macht keine arithmetischen Aggregationen mehr
- [ ] `pre-commit` läuft durch
- [ ] Tests vorhanden und grün
