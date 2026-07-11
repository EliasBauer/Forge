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
│ ┌─ ProjectVisualization Card ───────────────────────────┐ │
│ │ Projektstatus auf einen Blick  [Legende grün/gelb/rot]│ │
│ │ Plan-WV vs. Ist je Kategorie                          │ │
│ │ ┌─ Balkendiagramm (siehe §5) ───────────────────────┐ │ │
│ └───────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

---

## 2. ProjectHeader

- Card: `bg-white rounded-lg border border-gray-200 shadow-sm`
- Titel: `text-[22px] font-semibold` (Projektname)
- Untertitel: `text-xs text-gray-500` (ID)
- Actions rechts: `Bearbeiten` (mit `IconPencil`), `Archivieren` (mit `IconArchive`)
  als sekundäre Buttons
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
| 2  | Soll-Offerte (11 %)    | **User-Eingabe** | **ja**     |
| 3  | %  (6 %)               | berechnet        | nein       |
| 4  | Soll-WV (11 %)         | berechnet        | nein       |
| 5  | %  (6 %)               | berechnet        | nein       |
| 6  | Plan-WV (11 %)         | berechnet        | nein       |
| 7  | %  (6 %)               | berechnet        | nein       |
| 8  | Ist (11 %)             | ERP (read-only)  | nein       |
| 9  | %  (6 %)               | ERP              | nein       |

Spalten-Hintergründe:
- Soll-Offerte (Sp. 2): weiss (editierbar)
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

## 5. ProjectVisualization (Balkendiagramm)

Card mit:
- Header: „Projektstatus auf einen Blick"
- Health-Legende rechts: Status-Counts grün / gelb / rot mit Anzahl Kategorien
- Section-Titel: „Plan-WV vs. Ist je Kategorie"

### 5.1 Pro Kategorie

Grid `[160px 1fr 120px] gap-4`:

```
[Kategorie-Label]   ┌─────────────────────────┐   [Status-Pill]
                    │ Plan-WV ▓▓▓░░░░         │ CHF 1'215.06
                    │ Ist     ▓▓▓▓▓▓▓│        │ CHF 2'541.10
                    └─────────────────────────┘
                              ↑ Plan-WV-Marker
```

Beide Balken:
- Höhe `h-2.5`, `rounded-sm`, Hintergrund `bg-gray-100`
- Plan-WV-Balken: `bg-gray-300`
- Ist-Balken: `DEV_STYLES[level].dot` (oder `bg-gray-400` wenn keine Bewertung möglich)
- Beide auf **gemeinsamer Skala** (max aller `planWV` und `ist` der dargestellten Kategorien)

Auf der Ist-Spur zusätzlich: 1 px senkrechte Linie an der Plan-WV-Position
(`absolute top-[-2px] bottom-[-2px] w-px bg-gray-500/70`) — als 100 %-Marker.

### 5.2 Status-Pill (rechts)

```tsx
<span className={`inline-flex items-center gap-1.5 text-[11px] font-medium
                  tabular-nums ${DEV_STYLES[level].text}`}>
  {level === "over" || level === "warn" ? <IconWarning /> : <IconCheck />}
  {sign}{Math.abs(overPct).toFixed(1)} %
</span>
```

Wenn `ist === null && soll !== null`: kursives „noch offen" in `text-gray-400`.

### 5.3 Welche Kategorien angezeigt werden

Nur **nicht-locked** Zeilen mit **mindestens einem** Wert (`soll` oder `ist`)
erscheinen im Diagramm.

---

## 6. Akzeptanzkriterien (seite-spezifisch)

- [ ] Sticky Table-Header bleibt **unter** der Navbar (top: 56 px) — kein Stack-Overlap
- [ ] EditableMoneyCell: Enter / Escape / Blur korrekt, Apostroph-Eingabe akzeptiert
- [ ] Heatmap-BG überschreibt `.erp-tint` (nicht zusätzlich)
- [ ] „Differenz zu vorherigem"-Zeile zeigt 3 Deltas in den richtigen Spalten-Paaren
- [ ] Ist-vs-Plan-Δ ist visuell grün wenn IST unter Plan (polarity-Flag korrekt gesetzt)
- [ ] Soll-Total ändert sich live wenn eine Soll-Zelle editiert wird (alle abhängigen Spalten ebenfalls)
- [ ] Visualisierung zeigt keine locked rows
- [ ] „Bearbeiten" / „Archivieren" oben rechts rendern (Action TBD — klick öffnet später Modal)
