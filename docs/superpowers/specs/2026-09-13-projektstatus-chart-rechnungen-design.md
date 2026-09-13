# Projektstatus-Chart, Projektstatus-Spalte und Rechnungen-Pop-up

Datum: 2026-09-13 · Status: entworfen, wartet auf Review

## Ziel

Auf der Projektdetailseite soll auf einen Blick sichtbar sein, wie viel vom
Plan-WV noch offen ist (Plan-WV − AK verrechnet), wie weit die kumulierten
Ist-Kosten sind und ob sie den Plan-WV überschreiten. Dieselbe Kennzahl
erscheint als Miniatur in der Projektliste. Ausserdem sollen die Ist-Werte
(ERP) in der Kostenpositionen-Tabelle anklickbar werden und die zugrunde
liegenden Lieferantenrechnungen in einem Pop-up zeigen.

Nebenbei: `ProjektStatus` wird zu `ProjektPhase` umbenannt, damit der Begriff
„Projektstatus" frei wird für die neue Finanzkennzahl.

## Fachliche Definitionen

| Begriff | Quelle heute | Quelle später |
| --- | --- | --- |
| Soll-WV | `Projekt.wv_summe` | unverändert |
| Plan-WV | `Projekt.wv_summe` (Plan-WV = WV, bis Backend Zusätze liefert) | eigenes Feld / Kennzahl |
| Ist-Kosten kum. | `ProjektKennzahlen.summe_ist_kosten` (alle Lieferantenrechnungen des Projekts, netto) | unverändert |
| AK verrechnet | konstant `0` im Frontend | Kennzahl aus Backend (A-Konto-Zahlungen an Kunde) |
| Offen | Plan-WV − min(AK verrechnet, Plan-WV) | unverändert |
| Offen % | Offen / Plan-WV × 100 | unverändert |

„AK verrechnet" kann fachlich nie grösser als Plan-WV sein (man verrechnet
nicht mehr als Plan-WV). Liefert das Backend dennoch mehr, wird der Balken
gedeckelt und die Zahl mit dem Hinweis „gedeckelt" gezeigt.

## Task 0 · Umbenennen `ProjektStatus` → `ProjektPhase`

Rein mechanisch, eigener Commit vor allem anderen.

**Backend**

- `apps/projekt/models/projekt_status.py` → `projekt_phase.py`, Klasse
  `ProjektPhase`, `verbose_name` „Projekt-Phase", `db_table`
  `projekt_projektphase`. Werte (Offen / In Arbeit / Fertig) unverändert.
- `Projekt.projekt_status` → `Projekt.projekt_phase` (FK auf
  `projekt.ProjektPhase`, `related_name="projekte"` bleibt).
- Zwei Migrationen: `RenameModel` für `ProjektStatus` und
  `HistoricalProjektStatus`, `AlterModelTable`, `RenameField` auf `Projekt`
  und `HistoricalProjekt`. Daten bleiben erhalten.
- Admin (`list_display`, `list_filter`), `models/__init__.py`, `conftest.py`
  (`_seed_projekt_status` → `_seed_projekt_phase`), alle Tests.
- `forge/graphql_metric_operations.py`: `ProjektStatusIds` → `ProjektPhaseIds`.
- `docs/specs/projekt.md`: Feld- und Spaltennamen anpassen. Historische
  Specs/Pläne unter `docs/superpowers/` bleiben unverändert.

**GraphQL (autogeneriert, ergibt sich aus dem Rename)**

`projektStatus` → `projektPhase`, `projektStatusList` → `projektPhaseList`,
Mutation-Argument `projektStatus` → `projektPhase`.

**Frontend**

`queries.ts` (`GET_PROJEKT_STATUS_IDS` → `GET_PROJEKT_PHASE_IDS`, Operation
`ProjektPhaseIds`), `mutations.ts`, `ProjektListePage` (Spaltenkopf „Status"
→ „Phase"), `ProjektDetailPage` (Header-Feld „Status" → „Phase"),
`ProjektNeuPage`, zugehörige Tests.

## Task 1 · Backend: Rechnungslisten als GraphQL-Properties

Die Zuordnung Rechnung → Projekt → Kostenart bleibt vollständig im Backend.
Das Frontend kennt keine Kontonummern.

### `IstWert.rechnungen -> list[Lieferantenrechnung]`

- Neuer `@cached`-Helfer `_rechnungen() -> tuple[Lieferantenrechnung, ...]`
  enthält die heutige Auswahl-Logik aus `ist_kosten_wert` (Ertragsblock,
  `stunden`, `transport_montage` → leer; `diverses` → unbekannte oder fehlende
  Konten; sonst Konto-Nummer der Kostenart).
- `ist_kosten_wert` summiert `betrag − steuer_berechnet` über `_rechnungen()`;
  leer → `None` (Verhalten unverändert).
- `rechnungen` (`@graph_ql_property`) gibt `list(self._rechnungen())` zurück.
  Damit ist per Konstruktion garantiert, dass die Pop-up-Zeilen exakt den
  Ist-Wert der Zelle ergeben.
- Permission: `IstWert.__read__` ist bereits `isForgeAdmin, isProjektleiter`
  — identisch mit `Lieferantenrechnung`.

### `ProjektKennzahlen.rechnungen -> list[Lieferantenrechnung]`

Die Gesamtliste hängt an `ProjektKennzahlen`, nicht an `Projekt`: dieser
Manager importiert `Lieferantenrechnung` bereits auf Modulebene und berechnet
mit `_summe_ist()` genau dieselbe Menge. Auf `Projekt` wäre ein
Modulebenen-Import von Bexio nötig (die Return-Annotation muss zur Laufzeit
auflösbar sein, ein `TYPE_CHECKING`-Import genügt GM nicht) — und
`apps/projekt/models/` wird mitten in `apps.populate()` geladen.

- Neuer `@cached`-Helfer `_rechnungen() -> tuple[Lieferantenrechnung, ...]`;
  `_summe_ist()` summiert darüber, `rechnungen` gibt die Liste zurück.
- Attribut-Override in `ProjektKennzahlen.Permission`:
  `rechnungen = {"read": ["isForgeAdmin", "isProjektleiter"]}`. Nötig, weil
  `__read__` dieses Managers auch `isBetrachter` enthält, `Lieferantenrechnung`
  aber nicht — ohne Override würde ein Betrachter Rechnungen sehen (genau der
  Fehler, den 5180928 behoben hat).

**Verifiziert** (Spike gegen das echte Schema, danach zurückgebaut):
`list[Lieferantenrechnung]` erzeugt das Feld `[LieferantenrechnungType]`; über
GraphQL liefert ein Betrachter `rechnungen: null`, ein Projektleiter `[]`.

### Tests (pytest, `src/apps/projekt/tests/`)

- `IstWert.rechnungen`: Kategorie mit Konto, `diverses`, leere Kategorien
  (Ertragsblock/Stunden/Transport), Summe der Liste == `ist_kosten_wert`.
- `ProjektKennzahlen.rechnungen`: enthält Rechnungen aller Konten inkl. 44401
  und ohne Konto; Summe == `summe_ist_kosten`; Fremdprojekt-Rechnungen fehlen.
- GraphQL: Betrachter erhält für `projektKennzahlenList { items { rechnungen } }`
  eine Permission-Verweigerung; Projektleiter erhält die Liste.
- `tests/test_permission_konventionen.py` bleibt grün.

## Task 2 · Frontend-Grundlagen

### Design-Tokens (`frontend/src/index.css`)

- `--forge-blue-light: #93A7FA` (Soll-WV-Segment, „offen" im Mini-Balken)
- `--forge-green: #059669` (AK verrechnet)

### `utils/projektStatus.ts` (reine Funktion, keine React-Abhängigkeit)

```ts
type ProjektStatusInput = { planWV: number | null; sollWV: number | null; ist: number; ak: number };
type ProjektStatusResult = {
  scale: number;                 // max(planWV, sollWV, ist), mindestens 1
  planPct: number;               // planWV / scale × 100
  segments: {                    // Plan-WV-Linie, in Prozent von scale
    sollLight: [number, number]; // hellblau: 0 → min(soll, plan)
    fillDark:  [number, number]; // dunkelblau: soll → plan (nur wenn plan > soll)
    sollGhost: [number, number]; // hellblau gestrichelt: plan → soll (nur wenn soll > plan)
    overrun:   [number, number]; // rot gestrichelt: plan → ist (nur wenn ist > plan)
  };
  istPct: number;                // ist / scale × 100
  istOverPlan: boolean;
  istOverPlanAbs: number;        // ist − planWV (nur wenn istOverPlan)
  istOverPlanPct: number;        // (ist − planWV) / planWV × 100
  akPct: number;                 // min(ak, plan) / scale × 100
  akCapped: boolean;             // ak > planWV
  offen: number;                 // planWV − min(ak, planWV)
  offenPct: number;              // offen / planWV × 100
} | null;                        // null wenn planWV null oder 0
```

Vitest deckt die sechs abgenommenen Fälle ab: Normalfall, Soll = Plan,
Ist > Plan, voll verrechnet, AK > Plan (gedeckelt), Plan < Soll, sowie
`planWV` null.

## Task 3 · Chart „Projektstatus auf einen Blick" (Detailseite)

Neue Komponente `components/ProjektStatusChart.tsx`. Props: `planWV`,
`sollWV`, `ist`, `ak` (Detailseite übergibt `wvSumme`, `wvSumme`,
`summeIstKosten`, `0`).

**Layout** (abgenommene Variante A, alle Linien gleich dick, 10 px):

- Karte im Stil der bestehenden Karten; Header „Projektstatus auf einen
  Blick", rechts die Legende: Soll-WV · Auffüllung bis Plan-WV · Ist-Kosten
  kum. · AK verrechnet · Überschreitung Plan-WV.
- Body: links drei Zeilen (Label 120 px · Linie · Zahl 130 px rechtsbündig),
  rechts eine abgesetzte „Offen"-Kachel (Trennlinie links): Label „Offen
  (Plan-WV − AK)", Betrag gross, „x.x % von Plan-WV" darunter.
- Zeile Plan-WV: Segmente aus `projektStatus.ts`; Zahl fett.
- Zeile Ist-Kosten kum.: rote Linie; bei Überschreitung Zahl rot mit „⚠"
  und in der Offen-Kachel Zusatzzeile „Ist über Plan-WV: +CHF x (+y %)".
- Zeile AK verrechnet: grüne Linie, gedeckelt bei Plan-WV; Zahl zeigt den
  echten Wert, bei Deckelung mit Hinweis „gedeckelt"; bei 0 grau.
- In Ist- und AK-Zeile ein dünner senkrechter Plan-WV-Marker an `planPct`.
- `planWV` null → Karte mit Hinweis „Keine WV-Summe erfasst — Plan-WV fehlt."
- Sichtbar nur mit `canViewKostenPositionen` (wie die bestehende Karte).

**Einbau** in `ProjektDetailPage`, Reihenfolge von oben nach unten:
Kostenpositionen-Karte → neues Chart „Projektstatus auf einen Blick" →
bestehende Karte, umbenannt in „Projektkategorien auf einen Blick".
Spaltenkopf „Soll-Offerte" → „Offerte".

## Task 4 · Projektliste

- Spalte „Abweichung zu Ist" → **„Projektstatus"**, Inhalt
  `components/ProjektStatusMini.tsx` (Mini-Balken 110 px, 6 px hoch): hellblau
  = offen (volle Breite Plan-WV), grün = AK verrechnet, roter Strich = Ist
  (bei Ist > Plan am rechten Rand, 4 px breit). Daneben Text
  „130'000 offen · 52 %"; bei Ist > Plan-WV der gesamte Text rot mit „⚠"
  am Ende. `wvSumme` null → kursiv „keine WV-Summe".
- Spalte „WV + Zusätze" → **„Plan-WV"**; Wert weiterhin `summeWvPlus`.
- Spalte „Status" → „Phase" (Task 0).
- `DeviationCell` entfällt; `getDeviation`/`DEV_STYLES` bleiben für die
  Detailseite.
- `GET_PROJEKTE` bleibt unverändert (`wvSumme`, `summeIstKosten`,
  `summeWvPlus` sind bereits dabei).

## Task 5 · Rechnungen-Pop-up (Detailseite)

### Query

`GET_PROJEKT_RECHNUNGEN($id: ID!)`, Operation `ProjektRechnungen` (in die
Metrik-Allowlist aufnehmen):

```graphql
projekt(id: $id) {
  id
  projektKennzahlenList { items { rechnungen { ...RechnungFelder } } }
  istWertList { items { kostenart { schluessel } rechnungen { ...RechnungFelder } } }
}
```

Felder: `id dokumentNr rechnungsdatum firmenname zeilenTitel status
faelligkeitsdatum ueberfaellig betrag steuerBerechnet nettoBetrag` plus
`buchungskonto { accountNo name }`.

**Verifiziert:** `buchungskonto` ist entgegen der Faustregel der
`frontend`-Skill (»ForeignKey = String«) ein echter `KontoType` und verlangt
eine Sub-Selection — ohne sie antwortet der Server mit HTTP 400. `Konto` ist
für `isForgeAdmin`/`isProjektleiter` lesbar, passt also zur Query.

Ausgeführt per `useLazyQuery` mit `fetchPolicy: "no-cache"` — jedes Öffnen
lädt frisch. Grund: Die Query teilt sich Felder unter `projekt(id)` mit
`GET_PROJEKT`, deren `items`-Arrays keine `id` tragen und daher nicht
normalisierbar sind; ein gemeinsamer Cache-Eintrag würde sich gegenseitig
überschreiben (Details im Begründungskommentar in `ProjektDetailPage.tsx`
über der Query-Definition).

### Klickbarkeit

- Eine Ist-Zelle in der Kostenpositionen-Tabelle ist anklickbar genau dann,
  wenn sie einen Wert zeigt (`istKostenWert != null`). Damit sind
  Regie/Nachtrag, Stunden, Transport und Montage sowie Gemeinkosten
  automatisch nicht klickbar; für Kategorien ohne Rechnungen gibt es nichts
  zu zeigen. Klickbare Zellen: `cursor-pointer`, gepunktete Unterstreichung
  beim Hover, `role="button"`, per Tastatur erreichbar.
- Die Ist-Zelle in der Zeile „Summe der Kosten" öffnet die Gesamtliste, wenn
  `summeIstKosten > 0`.

### `components/RechnungenModal.tsx`

- Props: `title`, `rows`, `loading`, `error`, `onClose`.
- Overlay über der Seite, Dialog max. 1100 px breit, Schliessen per ✕,
  Escape und Klick auf das Overlay. `role="dialog"`, `aria-modal`, Fokus auf
  den Dialog beim Öffnen.
- Titel: „Rechnungen · Apparate" bzw. „Alle Rechnungen · <Projektname>".
- Tabelle, Spalten in dieser Reihenfolge: Datum · Dokument-Nr · Lieferant ·
  Zeilentitel · Buchungskonto · Status · Fällig am · Brutto · Steuer · Netto.
  Beträge über `chf()` ohne Währungspräfix, rechtsbündig, `tabular-nums`.
  „Fällig am" bei `ueberfaellig` rot mit „⚠".
- Sortierung client-seitig per Klick auf den Spaltenkopf: erster Klick
  absteigend für Datum/Beträge, aufsteigend für Text; zweiter Klick dreht.
  Pfeil-Indikator am aktiven Kopf. Default: Datum absteigend, dann Dokument-Nr.
- Fusszeile: „n Rechnungen · Netto CHF x" (Summe über `nettoBetrag` der
  Zeilen).
- Leerzustand „Keine Rechnungen", Ladezustand „Lade Rechnungen…", Fehler im
  bestehenden `errorStyle`.

### Tests (vitest)

- Ist-Zelle mit Wert öffnet Modal mit Kategorie-Titel und den Zeilen der
  passenden `istWertList`-Kategorie; Zelle ohne Wert ist nicht klickbar.
- Summe-Zelle öffnet Modal mit allen Rechnungen.
- Sortierung per Spaltenkopf dreht die Reihenfolge.
- Schliessen per ✕ und Escape.

## Nicht in diesem Vorhaben

- Gemeinkosten-Ist (eigener Branch).
- AK verrechnet aus dem Backend (Wert bleibt 0).
- Plan-WV getrennt von WV-Summe.
- Server-seitige Sortierung/Pagination der Rechnungen (Listen sind pro
  Projekt klein; bei Bedarf später als `_list`-Bucket mit `orderBy`).

## Abschluss

Volles Gate `pre-commit run --all-files` (ruff, mypy, pytest, vitest) grün;
Plan-Datei wird mit jedem Task-Commit abgehakt.
