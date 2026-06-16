# Seite: Todo (`/todo`)

Dashboard für offene Punkte, die Aufmerksamkeit brauchen. **Datengetrieben** und
auf Wachstum ausgelegt: aktuell gibt es genau **einen** Backend-Check (fehlende
Stundensätze); weitere Gruppen kommen später hinzu, ohne dass sich das Layout ändert.

> Voraussetzungen: [Design-System](./design-system.md), [Shared Components](./shared-components.md)

---

## 1. Layout

```
┌───────────────────────────────────────────────────────────┐
│ <Navbar active="todo" />                                  │
├───────────────────────────────────────────────────────────┤
│ Todo                                                      │
│ 1 offener Punkt                                           │
│                                                           │
│ ┌─ Gruppen-Card ────────────────────────────────────────┐ │
│ │ [🕐]  Fehlende Stundensätze   (1)                     │ │  ← Icon + Titel + Count-Badge
│ │       Für diese Jahre ist noch kein Stundensatz …     │ │  ← Beschreibung
│ │ ───────────────────────────────────────────────────── │ │
│ │ [2025]  Jahr 2025                  Stundensatz erfassen ›│ │  ← ein Item
│ └───────────────────────────────────────────────────────┘ │
│ (weitere Gruppen-Cards untereinander, space-y-4)          │
└───────────────────────────────────────────────────────────┘
```

---

## 2. Datenmodell (datengetrieben)

Die ganze Seite rendert aus einem Array von Gruppen. **Eine Gruppe = ein
Backend-Check.** Neue Checks → einfach ein Objekt anhängen, nichts am Layout ändern.

```ts
type Tone = "amber" | "blue" | "rose";

interface TodoItem {
  id: string;
  label: string;      // z.B. "2025" (im Chip)
  title: string;      // z.B. "Jahr 2025"
  sub: string;        // z.B. "Noch kein Stundensatz erfasst"
  href: string;       // Ziel zum Beheben, z.B. "/stundensaetze"
  action: string;     // CTA-Text, z.B. "Stundensatz erfassen"
}

interface TodoGroup {
  id: string;
  tone: Tone;         // Farb-Ton je Dringlichkeit/Art
  icon: IconComponent;
  title: string;      // z.B. "Fehlende Stundensätze"
  description: string;
  items: TodoItem[];
}
```

`tone` mappt auf ein Set Tailwind-Klassen (Icon-BG/-Text, Badge, Row-Hover,
Akzent). Im Prototyp definiert als `TONES[tone]`.

---

## 3. Gruppen-Card

- Container: `bg-white rounded-lg border border-gray-200 shadow-sm`
- **Header** (`border-b border-gray-100`):
  - Icon in abgerundetem Quadrat (`w-10 h-10 rounded-lg`, `tone.iconBg` + `tone.iconText`)
  - Titel `text-[15px] font-semibold` + **Count-Badge** (Anzahl Items, `tone.badge`,
    `rounded-full min-w-5`)
  - Beschreibung `text-sm text-gray-500` darunter
- **Items** als `<ul>`: jede Zeile ist ein `<a href={item.href}>`:
  - Chip links (`w-9 h-9 rounded-md`, Border in `tone.chipBorder`) mit `item.label`
  - Mitte: `item.title` (`text-sm font-medium`) + `item.sub` (`text-[12px] text-gray-500`)
  - Rechts: `item.action` + `IconChevronRight` in `tone.accent`,
    `opacity-70 group-hover:opacity-100`, Chevron verschiebt sich bei Hover leicht
  - Row-Hover: `tone.rowHover`
  - `border-b border-gray-100` zwischen Items, letztes ohne

---

## 4. Empty State („Alles erledigt")

Wenn keine Gruppen/Items offen sind:
- Card mit grünem `IconCheckCircle` (64 px) in `text-emerald-500`
- „Alles erledigt" (`text-[15px] font-semibold`)
- „Aktuell sind keine offenen Punkte vorhanden. Neue Hinweise erscheinen hier
  automatisch." (`text-sm text-gray-500`)
- Titel-Zähler zeigt „Keine offenen Punkte"

---

## 5. Zähler (Titelzeile)

Summe aller Items über alle Gruppen:
- 0 → „Keine offenen Punkte"
- 1 → „1 offener Punkt"
- N → „N offene Punkte"

---

## 6. API

```ts
GET /api/todo → TodoGroup[]
```

Aktuell liefert das Backend nur die Gruppe `stundensaetze` (abgeleitet aus den
fehlenden Jahren, vgl. [Stundensätze](./stundensaetze.md#3-lücken-erkennung-zentrales-feature)).
Die Seite darf beliebig viele Gruppen rendern.

### Beispiele künftiger Gruppen (nicht jetzt bauen — nur als Referenz für `tone`/Struktur)

| Gruppe                          | tone   | Quelle                          |
|---------------------------------|--------|---------------------------------|
| Projekte ohne Projektleiter     | blue   | `leiter === null`               |
| Plan-Überschreitung (Ist > Plan-WV) | rose | Kostenanalyse je Projekt        |

---

## 7. Akzeptanzkriterien (seite-spezifisch)

- [ ] Seite rendert vollständig aus dem `TodoGroup[]`-Array (keine fest verdrahtete Gruppe)
- [ ] Count-Badge pro Gruppe = Anzahl Items
- [ ] Titel-Zähler korrekt singular/plural
- [ ] Item-Klick navigiert zum `href` (z.B. fehlender Stundensatz → `/stundensaetze`)
- [ ] „Alles erledigt"-Zustand bei leerer Liste mit grünem Häkchen
- [ ] Tonfarbe (amber/blue/rose) kommt aus `tone`, nicht hartcodiert pro Gruppe
- [ ] Kein „Demo-Toggle" im Produktivcode (war nur Prototyp-Hilfe)
