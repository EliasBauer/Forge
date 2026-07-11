# Seite: Projektübersicht (`/projekte`)

Liste aller Projekte in tabellarischer Form. Direkter Einstiegspunkt nach Login
(„Projekte"-Tab in der [Navbar](./shared-components.md#navbar-active-)).

> Voraussetzungen: [Design-System](./design-system.md), [Shared Components](./shared-components.md)

---

## 1. Layout

```
┌───────────────────────────────────────────────────────────┐
│ <Navbar active="projekte" />                              │
├───────────────────────────────────────────────────────────┤
│ Container: max-w-[1280px] mx-auto px-6 py-6               │
│                                                           │
│ ┌─ Projekte ──────────────── [+ Neues Projekt] (blau) ──┐ │
│ │ 12 Projekte                                           │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                           │
│ ┌─ Tabelle (white card, rounded-lg, shadow-sm) ─────────┐ │
│ │ [🔍 Suchen…]   (Toolbar-Zeile, oben in der Card)      │ │
│ ├───────────────────────────────────────────────────────┤ │
│ │ Auftragsnr │ Name │ Projektleiter │ Offerte │ WV+Zus. │ │
│ │            │ Abweichung zu Ist │ Status              │ │
│ │ … Rows …                                              │ │
│ └───────────────────────────────────────────────────────┘ │
│ Hint-Text (klein, grau)                                   │
└───────────────────────────────────────────────────────────┘
```

---

## 2. Suche (Toolbar)

Eine Textsuche sitzt als eigene Zeile **oben in der Tabellen-Card** (mit `border-b`
zur Tabelle abgegrenzt — gehört visuell zur Tabelle, nicht freistehend darüber).

- Eingabefeld `max-w-sm` (nicht volle Breite), Lupe-Icon links, Clear-Button (×)
  rechts sobald Text vorhanden
- Filtert live über **Name, Auftragsnummer und Projektleiter-Name**
  (case-insensitive, Teilstring)
- Projekt-Zähler unter dem Titel zeigt bei aktiver Suche „X von Y Projekte"
- Reiner Client-Filter über die geladene Liste (kein Server-Roundtrip)

Leeres Ergebnis → [Empty State](#7-empty-state), Such-Variante.

---

## 3. Tabelle: Spaltenspezifikation

| # | Header              | Sortierbar                  | Inhalt                                            |
|---|---------------------|-----------------------------|---------------------------------------------------|
| 1 | Auftragsnr.         | ja (default desc)           | Monospace, `text-gray-600`. Format `YYYY-NNN`     |
| 2 | Name                | ja                          | Bold gray-900. Hover: blauer Chevron rechts daneben |
| 3 | Projektleiter       | ja (unzugewiesen ans Ende)  | Avatar-Pill (Initialen + Name) ODER „Nicht zugewiesen" |
| 4 | Offerte             | ja (desc default)           | Rechtsbündig, tabular-nums, ohne `CHF`-Prefix     |
| 5 | WV + Zusätze        | ja (desc default)           | Rechtsbündig, tabular-nums, `–` wenn null         |
| 6 | Abweichung zu Ist   | nein                        | Mini-Balken + farbiges `±x.x %` (siehe §5)        |
| 7 | Status              | ja                          | Badge `Aktiv` / `Archiviert`                       |

Spaltenbreiten (via `<colgroup>`):
`10% / 28% / 16% / 12% / 12% / 12% / 10%`

Header-Labels mit `whitespace-nowrap`, damit Label + Sort-Chevron nicht umbrechen.

### 3.1 Zeilen-Verhalten

- `cursor-pointer`, `hover:bg-blue-50/50`
- Klick navigiert zu `/projekte/{id}` (Projektdetail)
- Hover-Chevron neben dem Namen wird sichtbar (`opacity 0 → 1`, kleine X-Verschiebung)
- `border-b border-gray-100` zwischen Zeilen, letzte Zeile ohne Border

---

## 4. Avatar (Projektleiter-Zelle)

Initialen-Kreis (28 × 28 px) + Name:

```tsx
<span className="inline-flex items-center gap-2">
  <span className={`w-7 h-7 rounded-full ${person.color}
                    inline-flex items-center justify-center
                    font-semibold text-[11px]`}>
    {person.initials}
  </span>
  <span className="text-sm text-gray-800">{person.name}</span>
</span>
```

Farb-Mapping pro Person kommt **vom Backend** (nicht client-side berechnen).
Format: zwei Tailwind-Klassen, z. B. `"bg-blue-100 text-blue-700"`.

### „Nicht zugewiesen"-Placeholder

Wenn `leiter === null`:

```tsx
<span className="inline-flex items-center gap-2 text-gray-400">
  <span className="w-7 h-7 rounded-full bg-gray-100 border border-dashed
                   border-gray-300 inline-flex items-center justify-center">
    <IconUser className="text-gray-400" />
  </span>
  <span className="text-[12px] italic">Nicht zugewiesen</span>
</span>
```

---

## 5. DeviationCell — „Abweichung zu Ist"

Visueller Indikator: kleiner horizontaler Balken mit Mittellinie als Null-Punkt.
Vergleicht **Ist gegen WV** (`getDeviation(wv, ist)`).

```
   ─────│─────       ← w-12 h-1.5 rounded-full bg-gray-100, Mittellinie 1px gray-400/60
       │▓▓▓          IST > WV → füllt nach rechts
   ▓▓▓│              IST < WV → füllt nach links
```

Logik (Verwendung von [`getDeviation`](./design-system.md#5-abweichungs-bewertung--getdeviationbaseline-actual)):

```ts
const dev = getDeviation(wv, ist);       // → { ratio, overPct, level }
const overflow = dev.overPct > 0;
const magnitude = Math.min(Math.abs(dev.overPct), 30) / 30; // sättigt bei ±30 %
const fillWidthPct = magnitude * 50;     // % der halben Spurbreite
const color = DEV_STYLES[dev.level].dot; // Bar-Farbe
```

Rechts vom Balken: Prozentzahl in `text-[12px] font-medium tabular-nums`,
Farbe = `DEV_STYLES[level].text`. Vorzeichenformat siehe [Design-System §3](./design-system.md#3-zahlen-formatter).

Wenn `wv === null || ist === null`: nur `–` in `text-gray-300`.

> ⚠️ **Edge Case `ist === 0`**: Ein gebuchter Ist-Wert von 0 erzeugt sonst
> `overPct = −100 %` und färbt grün. Behandle `ist === 0` (noch nichts verbraucht)
> wie `null` → zeige `–`, nicht „−100 %".

---

## 6. Sortierung

- Default: `nr` desc (neueste oben)
- Klick auf Header:
  - **Gleicher** Key → Richtung toggeln (asc ↔ desc)
  - **Neuer** Key → Default-Richtung (`offerte` und `wv` starten desc, alle anderen asc)
- Visual ([`IconSort`](./shared-components.md#icons)):
  - Inaktiv: 30 % Opacity beide Chevrons
  - Spalten-Hover: Chevrons werden vollständig sichtbar (Hint)
  - Aktiv: aktive Richtung 100 %, andere 30 %; Header-Text in `text-blue-700`
- Sortier-State **nicht** in URL persistieren (kein Bookmarking-Bedarf).
- Sortierung beim Projektleiter: unzugewiesene Projekte landen am Ende
  (`name || "\uffff"` als Sort-Key).
- Sortierung wird **auf das gefilterte** Ergebnis angewendet (erst Suche, dann Sort).

---

## 7. Empty State

Zwei Varianten im selben Wrapper (`px-6 py-16 flex flex-col items-center text-center`):

**a) Keine Daten** (`projects.length === 0`):

```
┌───────────────────────────┐
│         📁 (80 px)        │
│   Noch keine Projekte     │
│   Leg dein erstes Projekt │
│   an, um Offerten…        │
│  [+ Erstes Projekt …]     │
└───────────────────────────┘
```
Folder-Icon (`IconFolderEmpty`) in `text-gray-300`, CTA = primärer blauer Button.

**b) Suche ohne Treffer** (Liste gefiltert leer):

```
┌───────────────────────────┐
│         🔍 (klein)        │
│   Keine Treffer           │
│   Für „xyz" wurde kein    │
│   Projekt gefunden…       │
│  [Suche zurücksetzen]     │
└───────────────────────────┘
```
Lupe-Icon, sekundärer „Suche zurücksetzen"-Button. **Die Suchleiste bleibt
sichtbar**, damit man die Eingabe direkt korrigieren kann.

Headline `text-[15px] font-semibold text-gray-900`, Body `text-sm text-gray-500 max-w-xs`.

---

## 8. Datentypen

```ts
type ProjectStatus = "active" | "archived";

interface ProjectListItem {
  id: number;
  nr: string;             // "YYYY-NNN"
  name: string;
  leiter: Person | null;
  offerte: number;        // CHF, exkl. MwSt.
  wv: number | null;      // CHF, exkl. MwSt. — null wenn noch keine Werkverträge
  ist: number | null;     // CHF aus ERP — null wenn noch nichts gebucht
  status: ProjectStatus;
}

interface Person {
  id: string;
  name: string;
  initials: string;
  avatarColorClass: string; // z.B. "bg-blue-100 text-blue-700"
}
```

API:
```ts
GET /api/projekte → ProjectListItem[]
```

---

## 9. Akzeptanzkriterien (seite-spezifisch)

- [ ] Tabelle hat exakt 7 Spalten in der genannten Reihenfolge
- [ ] Suchleiste sitzt in der Card (mit `border-b`), `max-w-sm`, filtert Name/Nr./Projektleiter
- [ ] Clear-Button (×) erscheint nur bei vorhandenem Suchtext
- [ ] Klick auf Zeile (nicht nur Name) navigiert zu Detail-Seite
- [ ] Avatar-Placeholder ist optisch eindeutig als „leer" erkennbar (gestrichelter Border)
- [ ] DeviationCell zentriert visuell auf Null (Mittellinie sichtbar), sättigt bei ±30 %
- [ ] `ist === 0` wird wie `null` behandelt (zeigt `–`, nicht „−100 %")
- [ ] Sortier-Indikator hat 3 Zustände: idle, hover, active-with-direction
- [ ] Header-Labels brechen nicht um (`whitespace-nowrap`)
- [ ] Empty State: Daten-Variante nur bei wirklich leerer Liste, Such-Variante bei 0 Treffern
- [ ] „+ Neues Projekt"-Button öffnet Modal (Action TBD — Button rendert, klickt aber noch nichts an)
