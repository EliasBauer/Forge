# Seite: Projektdetail (`/projekte/:id`)

Detail-Ansicht eines einzelnen Projekts mit Kosten-Aufschlüsselung (editierbare
Soll-Werte, abgeleitete Werkvertrags- und Plan-Werte, ERP-IST-Werte) und einer
Visualisierungs-Sektion.

> Voraussetzungen: [Design-System](./design-system.md), [Shared Components](./shared-components.md)

---

## 1. Layout

```
┌───────────────────────────────────────────────────────────┐
│ <Navbar active="projekte" />                              │
├───────────────────────────────────────────────────────────┤
│ ← Projekte (Breadcrumb, klein, klickbar)                  │
│                                                           │
│ ┌─ ProjectHeader Card ──────────────────────────────────┐ │
│ │ Titel · ID                       [Bearbeiten][Archiv] │ │
│ │ ───────────────────────────────────────────────────── │ │
│ │ Projektleiter│Jahr│Offerte│WV│Plan-WV  (5-col grid)   │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                           │
│ ┌─ CostTable Card ──────────────────────────────────────┐ │
│ │ Kostenpositionen   [Legende: editierbar/berechn./ERP] │ │
│ │ ┌─ 9-Spalten-Tabelle (siehe §3) ────────────────────┐ │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                           │
│ ┌─ ProjektStatusChart Card ─────────────────────────────┐ │
│ │ Projektstatus auf einen Blick     [Legende: 5 Swatches]│ │
│ │ ┌─ 3 Linien + „Offen“-Kachel (siehe §5) ─────────────┐│ │
│ └───────────────────────────────────────────────────────┘ │
│                                                           │
│ ┌─ ProjektKategorienChart Card ─────────────────────────┐ │
│ │ Projektkategorien auf einen Blick [Legende grün/gelb/rot]│
│ │ [Legende: Plan-WV · Ist-Kosten · Überschreitung]      │ │
│ │ ┌─ Balkendiagramm (siehe §6) ───────────────────────┐ │ │
│ └───────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

> Reihenfolge von oben nach unten: Kostenpositionen-Tabelle (§3) →
> Projektstatus auf einen Blick (§5, neu) → Projektkategorien auf einen
> Blick (§6, hiess vorher „Projektstatus auf einen Blick“).

---

## 2. ProjectHeader

- Card: `bg-white rounded-lg border border-gray-200 shadow-sm`
- Titel: `text-[22px] font-semibold` (Projektname)
- Untertitel: `text-xs text-gray-500` (ID)
- Actions rechts: `Bearbeiten` (mit `IconPencil`) als sekundärer Button —
  Status wird über ein Dropdown im Bearbeiten-Formular gesetzt, kein
  separater Archivieren-Button
- Border-Trenner, dann 5-Spalten-Grid mit Labels und Werten:
  - **Projektleiter** ([Avatar oder „–"](./projektuebersicht.md#3-avatar-projektleiter-zelle))
  - **Jahr**
  - **Offerte exkl. MwSt.** (CHF, formatiert mit `fmtCHF`)
  - **WV-Summe exkl. MwSt.**
  - **Plan-WV-Summe exkl. MwSt.**

Jedes Feld:
```tsx
<div className="text-[11px] uppercase tracking-wider text-gray-500 font-medium">
  {label}
</div>
<div className="mt-1 text-[15px] text-gray-900 tabular-nums">
  {value}
</div>
```

---

## 3. CostTable — zentrale Tabelle

### 3.1 Spalten (9 total)

| #  | Header (Spaltenbreite) | Quelle           | Editierbar |
|----|------------------------|------------------|------------|
| 1  | Art (24 %)             | Static (Label)   | nein       |
| 2  | Offerte (11 %)         | **User-Eingabe** | **ja**     |
| 3  | %  (6 %)               | berechnet        | nein       |
| 4  | Soll-WV (11 %)         | berechnet        | nein       |
| 5  | %  (6 %)               | berechnet        | nein       |
| 6  | Plan-WV (11 %)         | berechnet        | nein       |
| 7  | %  (6 %)               | berechnet        | nein       |
| 8  | Ist (11 %)             | ERP (read-only)  | nein       |
| 9  | %  (6 %)               | ERP              | nein       |

Spalten-Hintergründe:
- Offerte (Sp. 2): weiss (editierbar)
- Berechnete Spalten (3, 4, 5, 6, 7): `bg-gray-50 text-gray-500`
- ERP-Spalten (8, 9): `bg-blue-50 text-blue-700` (Klassen `.erp-tint` / `.erp-text`)

Spalten-Paar-Divider zwischen jedem (CHF, %)-Paar:
```css
.pair-divider { box-shadow: inset 1px 0 0 #e5e7eb; }
.pair-pad-l   { padding-left: 1.25rem; }
```

Stärkerer Divider zwischen Spalte 1 (Art) und Spalte 2:
```css
.cost-table thead th:nth-child(2),
.cost-table tbody td:nth-child(2),
.cost-table tfoot td:nth-child(2) {
  box-shadow: inset 2px 0 0 #d1d5db;
  padding-left: 1.5rem;
}
```

Sticky Header: `position: sticky; top: 56px;` (unter der Navbar).

### 3.2 Body-Zeilen

```ts
interface CostRow {
  id: string;
  label: string;
  soll: number | null;    // user input
  ist: number | null;     // aus ERP
  locked?: boolean;       // header rows: Soll-Offerte nicht editierbar
}
```

Die ersten 3 Zeilen sind **locked** (`M/MK`, `Regie`, `Nachtrag`):
- Hintergrund `bg-gray-50/70`
- Soll-Offerte-Zelle zeigt `–` in `text-gray-400`, kein EditableMoneyCell
- Trenner zwischen letzter Locked-Zeile und erster normaler Zeile: `border-gray-300`
  (statt `border-gray-100`)

### 3.3 Berechnung pro Zeile

```ts
const sollTotal  = sum(rows.map(r => r.soll ?? 0));
const wvFactor   = wvTotal / sollTotal;
const planFactor = planWVTotal / sollTotal;

for (const r of rows) {
  r.sollPct   = (r.soll / sollTotal) * 100;
  r.sollWV    = r.soll * wvFactor;          // proportional skaliert
  r.wvPct     = (r.sollWV / wvTotal) * 100;
  r.planWV    = r.soll * planFactor;
  r.planWVPct = (r.planWV / planWVTotal) * 100;
  r.istPct    = (r.ist / r.soll) * 100;     // Verbrauchsrate
}
```

Alle Berechnungen reaktiv auf Änderung von `soll` aktualisieren.

### 3.4 EditableMoneyCell

Idle-State:
- `<button>` mit Wert rechtsbündig (`tabular-nums`)
- `border border-gray-200`, hover `border-blue-400 bg-blue-50/40`
- `IconPencil` 0 % Opacity → 60 % bei Hover, rechts neben dem Wert

Edit-State (Klick öffnet Inline-Input):
- `<input type="text" inputMode="decimal">`
- `border-2 border-blue-500 shadow-[0_0_0_3px_rgba(59,130,246,0.15)]`
- Auto-Focus + Auto-Select beim Öffnen
- Enter → commit
- Escape → abbrechen (Wert zurücksetzen)
- Blur → commit

Input akzeptiert:
- `1'000` (Schweizer Apostroph)
- `1000`
- `1000,50` (Komma)
- `1000.50` (Punkt)

Leerer String → `null`.

### 3.5 Heatmap auf Ist-Zelle

Pro Zeile: `getDeviation(planWV, ist)` → Level → Hintergrundfarbe der Ist-Zellen
(Sp. 8 + 9) **überschreibt** das Default-`.erp-tint`:

| Level         | BG der Ist-Zellen   | Text                          | Icon vor Zahl |
|---------------|---------------------|-------------------------------|---------------|
| `over`        | `bg-rose-50`        | `text-rose-700 font-medium`   | `IconWarning` |
| `warn`        | `bg-amber-50`       | `text-amber-700 font-medium`  | `IconWarning` |
| `ok`, `under` | `bg-emerald-50/60`  | `text-emerald-700 font-medium`| —             |
| (kein Vergleich möglich) | `bg-blue-50` | `text-blue-700`         | —             |

Zusätzlich in Spalte 1 (Label): ein **Status-Dot** (1.5 × 1.5 px Kreis) **vor**
dem Label, Farbe = `DEV_STYLES[level].dot`.

### 3.6 Footer-Zeilen (`<tfoot>`)

Reihenfolge:

1. **Summe der Kosten** (`border-t-2 border-gray-300`, `font-semibold`)
   - Spalten füllen: Soll-Total, Σ%, Soll-WV-Total, Σ%, Plan-WV-Total, Σ%,
     Ist-Total, **Verbrauchsrate** = `istTotal / sollTotal × 100`

2. **Gewinn / Verlust**
   - Spalte 2: `<SignedAmount value={offerteTotal - sollTotal} />` (default polarity)
   - Spalte 4: `<SignedAmount value={wvTotal - sollWVTotal} />`
   - Spalte 6: `<SignedAmount value={planWVTotal - planWVSumTotal} />`

3. **Differenz zu vorherigem** (Treppen-Vergleich pro Paar)
   - Spalten 4+5: `(sollWVTotal − sollTotal)` als CHF + Δ% (default polarity)
   - Spalten 6+7: `(planWVTotal − sollWVTotal)` (default polarity)
   - Spalten 8+9: `(istTotal − planWVTotal)` mit **`polarity="pos-bad"`**
     (unter Plan = grün, weil weniger Kosten besser sind)

4. **Bisher verr. Total**
   - Spalte 8 (Ist): ERP-Summe der Ausgangsrechnungen, typisch negativ
   - `<SignedAmount value={bisherVerrTotal} strong />`

5. **Abgrenzung** + **Vorrat**: leere Platzhalter-Zeilen (Backend liefert später)

### 3.7 Legende (rechts oben in der Tabellen-Card)

Drei Mini-Swatches mit Beschriftung:
- `bg-white border border-gray-300` → „editierbar"
- `bg-gray-100 border border-gray-200` → „berechnet"
- `bg-blue-50 border border-blue-200` → „aus ERP"

### 3.8 Klickbare Ist-Zellen — Rechnungen-Pop-up

Eine Ist-Zelle ist klickbar, sobald sie einen Wert zeigt — es gibt **keine
gepflegte Ausnahmeliste**, die Klickbarkeit folgt allein aus dem
angezeigten Wert. Dass „Transport und Montage“, „Stunden“ und
„Gemeinkosten“ heute nie klickbar sind, ergibt sich daher von selbst: diese
Positionen zeigen aktuell nie einen Ist-Wert.

Klick öffnet ein Pop-up mit den Lieferantenrechnungen hinter genau dieser
Position. Die Ist-Zelle der Fusszeile „Summe der Kosten“ (§3.6) ist die
einzige Ausnahme in der *Zielmenge*, nicht in der Regel: sie öffnet alle
Rechnungen des Projekts statt der Rechnungen einer einzelnen Position.

Das Pop-up:
- lädt seine Daten bei **jedem** Öffnen frisch nach (kein Cache) — bewusste
  Entscheidung des Auftraggebers: man verweilt hier nicht, dafür sind die
  Zahlen immer aktuell
- zeigt eine Tabelle, die nach **jeder** Spalte sortierbar ist

**Berechtigung:** Lieferantenrechnungen liefert das Backend nur an Admin
und Projektleiter aus (general_manager-Permission, nicht im Frontend
geprüft). Einzelne Positionszeilen sieht ohnehin nur, wer Kostenpositionen
lesen darf — für diese Rollen ist die Rechnungsfrage also bereits durch die
Sichtbarkeit der Zeile entschieden. Die Fusszeile „Summe der Kosten“
dagegen bleibt für jede Rolle sichtbar, die die Projektkennzahlen lesen
darf (auch Betrachter, siehe [`projekt.md`](../projekt.md) für die
Rollentabelle); deren Ist-Zelle ist entsprechend ebenfalls klickbar — das
Pop-up liefert für sie aber ein leeres Ergebnis, weil das Rechnungen-Feld
serverseitig auf Admin/Projektleiter beschränkt ist.

---

## 4. API

```ts
GET   /api/projekte/:id      → ProjectDetail
PATCH /api/projekte/:id/rows/:rowId  { soll: number | null }
```

```ts
interface ProjectDetail {
  id: number;
  nr: string;
  name: string;
  leiter: Person | null;
  jahr: number;
  offerteTotal: number;
  wvTotal: number;
  planWVTotal: number;
  bisherVerrTotal: number;   // negativ = bereits ausgangsfakturiert
  rows: CostRow[];
}
```

Nur die `soll`-Spalte ist editierbar — alle anderen Werte ergeben sich aus
Berechnungen (im Client) oder kommen aus ERP (read-only).

Empfehlung: bei jeder Soll-Änderung optimistisches Update + PATCH; bei Server-Fehler
revertieren mit Toast.

---

## 5. ProjektStatusChart — Projektstatus auf einen Blick

Card zwischen der Kostenpositionen-Tabelle (§3) und der Kategorien-Karte
(§6). Sie fasst den finanziellen Gesamtstatus des Projekts in drei gleich
dicken Linien zusammen; die Aufschlüsselung je Kategorie bleibt Aufgabe von
§6. Sichtbar unter derselben Bedingung wie die einzelnen
Kostenpositionen-Zeilen (`canViewKostenPositionen`, heute Admin und
Projektleiter) — Betrachter sieht diese Karte nicht.

### 5.1 Drei Linien + „Offen“-Kachel

Grid mit den drei Linien links und einer abgesetzten Kachel rechts:

```
Plan-WV          ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░              CHF 393'319.37
Ist-Kosten kum.  ▓▓▓▓▓▓▓░░░░░░░░░░░░░              CHF 265'844.78    ┃ Offen (Plan-WV − AK)
AK verrechnet    ░░░░░░░░░░░░░░░░░░░░              CHF 0.00         ┃ CHF 393'319.37
                                                                     ┃ 100.0 % von Plan-WV
```

- **Plan-WV**: hellblau von 0 bis Soll-WV, dunkelblau als Auffüllung von
  Soll-WV bis Plan-WV (Normalfall Plan-WV ≥ Soll-WV; siehe Sonderfälle)
- **Ist-Kosten kum.**: rot
- **AK verrechnet**: grün — bisher dem Kunden verrechnete
  A-Konto-Zahlungen
- **Offen** (rechte Kachel) = Plan-WV − AK verrechnet, als CHF-Betrag und
  in Prozent von Plan-WV

Alle drei Linien teilen sich denselben Massstab
(`max(Plan-WV, Soll-WV, Ist)`), damit die Breiten vergleichbar bleiben.

### 5.2 Heutige Datenquellen (provisorisch)

| Kennzahl        | Quelle heute                                                        |
| --------------- | -------------------------------------------------------------------- |
| Plan-WV         | `summeWvPlus` (ProjektKennzahlen; dieselbe Kennzahl auf Detailseite und Projektliste) |
| Soll-WV         | `wvSumme` (ursprünglicher Werkvertragswert, dieselbe Zahl wie „WV-Summe exkl. MwSt.“ im Kopf) |
| Ist-Kosten kum. | `summeIstKosten` (= Fusszeile „Summe der Kosten“ der Kostentabelle)  |
| AK verrechnet   | fest `0` — das Backend liefert diesen Wert noch nicht                |

`summeWvPlus` (`summe_wv_plus` in `projekt_kennzahlen.py`) liefert heute
lediglich `wv_summe` zurück — Plan-WV und Soll-WV sind also aktuell
identisch, und die unten beschriebenen „Soll-WV ≠ Plan-WV“-Fälle treten in
der Praxis nicht auf. Die Komponente unterstützt sie bereits für den Tag,
an dem der dort vermerkte `TODO: Ertragsblock-Zusätze (Phase 2)` landet:
dann wächst Plan-WV über Soll-WV hinaus, und das dunkelblaue
„Auffüllung“-Segment (§5.1) bekommt seine eigentliche Bedeutung. Ebenso ist
„Offen“ heute für jedes Projekt immer 100 % von Plan-WV, weil AK verrechnet
konstant 0 ist.

### 5.3 Sonderfälle

- **Ist über Plan-WV**: der gemeinsame Massstab wächst auf den Ist-Wert;
  die Überschreitung erscheint in der Plan-WV-Linie gestrichelt rot, die
  Ist-Zahl wird rot mit „⚠“, und die Offen-Kachel bekommt eine Zusatzzeile
  „Ist über Plan-WV: +CHF … (+…%)“.
- **AK verrechnet über Plan-WV**: der grüne Balken wird bei Plan-WV
  gedeckelt (auch „Offen“ rechnet mit dem gedeckelten Wert und wird nie
  negativ); die angezeigte Zahl bleibt der echte AK-Wert, ergänzt um
  „gedeckelt“.
- **Soll-WV grösser als Plan-WV**: die Plan-WV-Linie zeigt dunkelblau bis
  Plan-WV, der Überhang bis Soll-WV erscheint hellblau gestrichelt.
- **Keine WV-Summe erfasst** (Plan-WV `null` oder ≤ 0): die Karte zeigt nur
  den Hinweis „Keine WV-Summe erfasst — Plan-WV fehlt.“ — weder Linien noch
  Legende.

Ist-Überschreitung und AK-Deckelung sind unabhängige Bedingungen und können
gleichzeitig auftreten.

---

## 6. ProjektKategorienChart (Balkendiagramm)

Card mit:
- Header: „Projektkategorien auf einen Blick" (hiess vor der Einführung
  von §5 „Projektstatus auf einen Blick")
- Health-Legende rechts: Status-Counts grün / gelb / rot mit Anzahl Kategorien
- Balken-Legende darunter: Plan-WV · Ist-Kosten · Überschreitung Plan-WV

### 6.1 Pro Kategorie

**Ein** Balken je Kategorie, gebaut wie die Plan-WV-Zeile des Projektstatus
(§5) — zwei getrennte Balken pro Kategorie standen vorher nebeneinander, ohne
dass die Farben etwas mit §5 zu tun hatten.

Grid `[180px 1fr 150px] gap-4`:

```
[● Kategorie-Label]   ┌─────────────────────────┐   CHF 2'541.10
[  Plan-WV CHF 1'215] │ ▓▓▓▓▓▓▓▓╱╱╱╱╱│          │   [Status-Pill]
                      └─────────────────────────┘
                        Plan-WV  über │ Ist-Linie
```

Balken (`h-2.5`, `rounded-sm`, Hintergrund `bg-gray-100`):
- `0 … planWV`: `var(--forge-blue-light)`, `rounded-sm`
- `planWV … ist`, nur wenn `ist > planWV`: `GESTRICHELT_ROT`
  (`utils/chartStyles.ts`, dasselbe Muster wie die Überschreitung in §5)
- senkrechte Linie an der Ist-Position: `w-px`, `var(--forge-red)`,
  `absolute top-[-3px] bottom-[-3px]` — auch wenn Ist unter Plan-WV liegt
- **Gemeinsame Skala** über alle Zeilen (max aller `planWV` und `ist` der
  dargestellten Kategorien), damit die Balkenlängen vergleichbar bleiben

Rechts: Ist-Betrag in `DEV_STYLES[level].text`, darunter die Status-Pill.

### 6.2 Status-Pill (rechts)

```tsx
<span className={`inline-flex items-center gap-1.5 text-[11px] font-medium
                  tabular-nums ${DEV_STYLES[level].text}`}>
  {level === "over" || level === "warn" ? <IconWarning /> : <IconCheck />}
  {sign}{Math.abs(overPct).toFixed(1)} %
</span>
```

Wenn `ist === null && soll !== null`: kursives „noch offen" in `text-gray-400`.

### 6.3 Welche Kategorien angezeigt werden

Nur **nicht-locked** Zeilen mit **mindestens einem** Wert (`soll` oder `ist`)
erscheinen im Diagramm.

---

## 7. Akzeptanzkriterien (seite-spezifisch)

- [ ] Sticky Table-Header bleibt **unter** der Navbar (top: 56 px) — kein Stack-Overlap
- [ ] EditableMoneyCell: Enter / Escape / Blur korrekt, Apostroph-Eingabe akzeptiert
- [ ] Heatmap-BG überschreibt `.erp-tint` (nicht zusätzlich)
- [ ] „Differenz zu vorherigem"-Zeile zeigt 3 Deltas in den richtigen Spalten-Paaren
- [ ] Ist-vs-Plan-Δ ist visuell grün wenn IST unter Plan (polarity-Flag korrekt gesetzt)
- [ ] Soll-Total ändert sich live wenn eine Soll-Zelle editiert wird (alle abhängigen Spalten ebenfalls)
- [ ] Visualisierung zeigt keine locked rows
- [ ] „Bearbeiten" oben rechts rendert; Klick öffnet das Edit-Formular inkl. Status-Dropdown
- [ ] ProjektStatusChart erscheint nur, wenn `canViewKostenPositionen` true ist (Betrachter sieht die Karte nicht)
- [ ] Ist > Plan-WV: Ist-Zeile rot mit „⚠", Überschreitung in der Plan-WV-Linie gestrichelt, Zusatzzeile in der Offen-Kachel
- [ ] AK verrechnet > Plan-WV: Balken bei Plan-WV gedeckelt, Zahl zeigt echten Wert + „gedeckelt"
- [ ] Ohne WV-Summe zeigt die Karte nur den Hinweistext, keine Linien
- [ ] Ist-Zellen mit Wert öffnen das Rechnungen-Pop-up; Fusszeile „Summe der Kosten" öffnet alle Rechnungen des Projekts
- [ ] Rechnungen-Pop-up lädt bei jedem Öffnen neu (kein veralteter Cache-Stand); Tabelle sortierbar nach jeder Spalte
