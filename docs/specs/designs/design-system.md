# Design-System

Gemeinsame Konventionen für Farben, Typografie, Zahlenformatierung, Vorzeichen,
Abweichungen und Status. Wird von **beiden** Seiten verwendet.

---

## 1. Farben (Tailwind-Token)

| Rolle               | Token              | Verwendung                                         |
|---------------------|--------------------|----------------------------------------------------|
| Primär              | `blue-600/700`     | CTA-Buttons, aktiver Nav-Tab, Akzentlinks          |
| Erfolg / Im Soll    | `emerald-500/600/700` | Positive Werte, „Aktiv"-Badge, im Plan          |
| Warnung             | `amber-500/600/700` | Grenzbereich-Abweichungen                          |
| Fehler / Übertreten | `rose-500/600/700` | Negative Werte (Verlust), Plan-Überschreitung      |
| Neutral             | `gray-50…900`      | Hintergründe, Text, Borders                        |
| ERP-Daten           | `blue-50` BG, `blue-700` Text | Hintergrund-Tint für alle Felder aus ERP |

Page-Background: `#f6f7f9`.

---

## 2. Typografie

- **Familie**: System-Stack (`-apple-system, "Segoe UI", system-ui, …`).
- **Tabular nums** (`font-variant-numeric: tabular-nums` bzw. Tailwind `tabular-nums`)
  zwingend auf allen Geldbeträgen und Prozentwerten.
- **Skala**:
  - H1 Seitentitel: `text-[22px] font-semibold text-gray-900`
  - Section-Titel: `text-[15px] font-semibold text-gray-900`
  - Body: `text-sm` (14 px)
  - Labels (Uppercase): `text-[11px] uppercase tracking-wider text-gray-500 font-medium`
  - Metadata sekundär: `text-[12px] text-gray-500`

---

## 3. Zahlen-Formatter

```ts
// CHF mit Schweizer Tausender-Apostroph; negativ = "−" (U+2212) + thin no-break space.
fmtCHF(12345)         // "CHF 12'345.00"
fmtCHF(-2345)         // "CHF −\u202F2'345.00"
fmtCHF(-2345, {withCurrency: false}) // "−\u202F2'345.00"
fmtCHF(null)          // "–"

// Prozent (1 Nachkommastelle)
fmtPct(19)            // "19.0 %"
fmtPct(null)          // "–"
```

Negativ-Format:
- Minuszeichen ist **U+2212**, nicht ASCII `-`.
- Zwischen Minus und Zahl ein **thin no-break space** (U+202F), damit nichts klebt.
- Zwischen `CHF` und Zahl ein normales non-breaking space (U+00A0).

---

## 4. Signed-Komponenten (Vorzeichenfarbe)

```tsx
<SignedAmount value={-2345} />                    // rot
<SignedAmount value={+5000} />                    // grün
<SignedAmount value={-3424} polarity="pos-bad" /> // grün! (negativ ist hier gut)
<SignedPct value={-22.8} polarity="pos-bad" />    // grün
```

Polarität:
- `"neg-bad"` (Default): negativ = rot, positiv = grün
- `"pos-bad"`: invertiert (für Felder wo „weniger ist besser" — z. B. Ist unter Plan)

---

## 5. Abweichungs-Bewertung — `getDeviation(baseline, actual)`

```ts
ratio = actual / baseline
ratio > 1.10 → "over"  (rot)
ratio > 1.00 → "warn"  (amber)
ratio ≥ 0.95 → "ok"    (grün)
ratio < 0.95 → "under" (grün)
```

Wird verwendet für:
- Zeilen-Heatmap in der Kostentabelle (Plan-WV vs. Ist je Position)
- „Abweichung zu Ist"-Spalte in der Projektübersicht (WV vs. Ist je Projekt)
- Status-Balkendiagramm „Plan-WV vs. Ist je Kategorie"

`DEV_STYLES` mappt Level → Tailwind-Klassen:

```ts
DEV_STYLES = {
  over:  { dot: "bg-rose-500",    text: "text-rose-700",    bg: "bg-rose-50",    label: "Überschritten" },
  warn:  { dot: "bg-amber-500",   text: "text-amber-700",   bg: "bg-amber-50",   label: "Grenzbereich" },
  ok:    { dot: "bg-emerald-500", text: "text-emerald-700", bg: "bg-emerald-50", label: "Im Soll" },
  under: { dot: "bg-emerald-500", text: "text-emerald-700", bg: "bg-emerald-50", label: "Unter Soll" },
}
```

---

## 6. Status (Projekt-Lifecycle)

Es gibt **nur zwei** Status:

| Status     | Label        | Visual                                  |
|------------|--------------|-----------------------------------------|
| `active`   | Aktiv        | Grüner Dot, emerald-50 BG, emerald-700 Text |
| `archived` | Archiviert   | Grauer Dot, gray-50 BG, gray-500 Text   |

(Frühere Status „In Verzug" und „Abgeschlossen" wurden bewusst entfernt — der
operative Zustand ergibt sich aus der Kostenanalyse, nicht aus einem Label.)

Badge-Markup:
```tsx
<span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px]
                 font-medium bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200">
  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
  Aktiv
</span>
```
