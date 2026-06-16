# Seite: Stundensätze (`/stundensaetze`)

Verwaltung der Stundensätze pro Jahr. Pro Jahr genau **ein** Satz (CHF/Stunde),
der zur Kostenberechnung der Projekte des jeweiligen Jahres dient.

> Voraussetzungen: [Design-System](./design-system.md), [Shared Components](./shared-components.md)

---

## 1. Layout

```
┌───────────────────────────────────────────────────────────┐
│ <Navbar active="stundensaetze" />                         │
├───────────────────────────────────────────────────────────┤
│ ┌─ Stundensätze ──────── [+ Neuer Stundensatz] (blau) ──┐ │
│ │ 3 Stundensätze · 1 Jahr ohne Satz (amber)             │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                           │
│ (optional) rote Fehlerzeile bei Validierungsfehler        │
│                                                           │
│ ┌─ Tabelle (white card, max-w-2xl) ─────────────────────┐ │
│ │ Jahr        │ CHF / Stunde        │ Aktionen          │ │
│ │ 2026        │ CHF 100.00          │ [Bearbeiten] [🗑]  │ │
│ │ ⚠ 2025      │ kein Satz hinterlegt│ [+ Erfassen]      │ │  ← Lücken-Zeile
│ │ 2024        │ CHF 95.00           │ [Bearbeiten] [🗑]  │ │
│ │ 2023        │ CHF 92.50           │ [Bearbeiten] [🗑]  │ │
│ └───────────────────────────────────────────────────────┘ │
│ Hint-Text → verlinkt auf Todo                             │
└───────────────────────────────────────────────────────────┘
```

Tabelle ist bewusst schmal (`max-w-2xl`) — kurze Datenmenge, keine volle Breite.
Sortierung: **immer Jahr absteigend** (neuestes oben), nicht umsortierbar.

---

## 2. Tabelle: Spalten

| Spalte       | Breite | Inhalt                                                   |
| ------------ | ------ | -------------------------------------------------------- |
| Jahr         | 30 %   | `tabular-nums`, `font-medium`                            |
| CHF / Stunde | 40 %   | Rechtsbündig, `fmtCHF(rate)`. Im Edit-Modus Inline-Input |
| Aktionen     | 30 %   | Rechtsbündig: „Bearbeiten" + Löschen (🗑, nur bei Hover)  |

---

## 3. Lücken-Erkennung (zentrales Feature)

Zwischen ältestem und neuestem erfassten Jahr wird **jedes fehlende Jahr** als
eigene „Lücken-Zeile" eingefügt. Generisch — funktioniert für jedes fehlende
Jahr, nicht nur das Beispiel 2025.

```ts
const years = rates.map(r => r.year);
const [min, max] = [Math.min(...years), Math.max(...years)];
const rows = [];
for (let y = max; y >= min; y--) {
  const found = rates.find(r => r.year === y);
  rows.push(found ? { type: "rate", ...found } : { type: "gap", year: y });
}
```

**Lücken-Zeile** (Darstellung):
- Zeilen-Hintergrund `bg-amber-50/60`, hover `bg-amber-50`
- Jahr mit `IconWarning` + `text-amber-700 font-medium`
- Mittelspalte: kursiv „kein Stundensatz hinterlegt" in `text-amber-700/80`
- Aktion: `+ Erfassen`-Button (amber, `border-amber-300 bg-white`) → öffnet die
  Eingabezeile **vorbefüllt mit genau diesem Jahr**

Der Zähler unter dem Titel zeigt zusätzlich „· N Jahr(e) ohne Satz" in `text-amber-600`.

> Damit ist der offene Punkt der [Todo-Seite](./aufgaben.md) genau dort sichtbar,
> wo man ihn behebt — die beiden Seiten spiegeln dieselbe Backend-Information.

---

## 4. Inline-Bearbeiten

„Bearbeiten" verwandelt die CHF-Zelle in ein Inline-Input:
- `border-2 border-blue-500 shadow-[0_0_0_3px_rgba(59,130,246,0.15)]`, Auto-Focus + Select
- Prefix „CHF" links vom Feld
- **Enter** oder **Blur** → committen; **Escape** → abbrechen
- Aktion wechselt zu „Fertig"
- Input akzeptiert `1'000`, `1000`, `95,50`, `95.50`

---

## 5. Neuanlage

„+ Neuer Stundensatz" (oder „+ Erfassen" einer Lücke) blendet oben in der Tabelle
eine **blau getönte Eingabezeile** ein:
- Jahr-Input (number) + CHF-Input
- Bei „Neuer Stundensatz": Jahr vorbelegt mit `max(jahr) + 1`
- Bei „Erfassen" aus einer Lücke: Jahr vorbelegt mit dem fehlenden Jahr
- Buttons „Speichern" (blau) + „Abbrechen"

### Validierung (rote Fehlerzeile oben, `bg-rose-50 border-rose-200`)
- Ungültiges Jahr (kein Integer, < 2000 oder > 2100) → „Bitte ein gültiges Jahr eingeben."
- Jahr existiert bereits → „Für {Jahr} existiert bereits ein Stundensatz."
- Fehlender / ungültiger Betrag → „Bitte einen gültigen Betrag eingeben."

---

## 6. Löschen

Papierkorb-Icon (`IconTrash`), nur sichtbar bei Zeilen-Hover
(`opacity-0 group-hover:opacity-100`), hover `text-rose-600 bg-rose-50`.
Entfernt den Satz; wird das Jahr dadurch zur Lücke zwischen zwei anderen Jahren,
erscheint automatisch die Lücken-Zeile.

---

## 7. Empty State

Wenn gar keine Sätze existieren (und nicht gerade hinzugefügt wird):
Uhr-Icon (`IconClock`, groß) in `text-gray-300`, „Noch keine Stundensätze",
Body-Text, primärer CTA „+ Ersten Stundensatz anlegen".

---

## 8. Datentypen & API

```ts
interface HourlyRate {
  year: number;   // z.B. 2026
  rate: number;   // CHF / Stunde
}
```

```ts
GET    /api/stundensaetze            → HourlyRate[]
POST   /api/stundensaetze            { year, rate }   // 409 wenn Jahr existiert
PATCH  /api/stundensaetze/:year      { rate }
DELETE /api/stundensaetze/:year
```

Die „Lücken" sind **rein clientseitig** abgeleitet (kein eigenes Backend-Feld).
Den Mock-Datensatz so wählen, dass mindestens ein Jahr fehlt (Beispiel: 2026,
2024, 2023 vorhanden → 2025 ist Lücke).

---

## 9. Akzeptanzkriterien (seite-spezifisch)

- [ ] Sortierung strikt Jahr absteigend, nicht umsortierbar
- [ ] Jedes fehlende Jahr zwischen min und max erzeugt eine amber Lücken-Zeile
- [ ] „Erfassen" einer Lücke öffnet die Eingabezeile mit korrekt vorbelegtem Jahr
- [ ] Zähler zeigt „· N Jahre ohne Satz" in amber, wenn Lücken existieren
- [ ] Inline-Edit: Enter / Blur committet, Escape verwirft
- [ ] Doppeltes Jahr beim Anlegen → rote Fehlermeldung, kein Speichern
- [ ] CHF-Eingabe akzeptiert Apostroph- und Komma-Schreibweise
- [ ] Löschen-Icon nur bei Hover sichtbar
- [ ] Hint-Text unten verlinkt auf `/todo`
