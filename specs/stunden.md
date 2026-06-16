# Spec: Stundensatz

## Ziel

Pro Kalenderjahr wird ein globaler Stundensatz hinterlegt.
Er wird für die Berechnung der Personalkosten unter „Transport und Montage" in der Projektübersicht verwendet:
`Stunden × Stundensatz des Jahres = CHF-Wert`.

Da Projekte mehrere Jahre laufen können, ist der Stundensatz jahresabhängig.

---

## Backend

### App: `apps.stunden`

**Abhängigkeiten:** keine (standalone; `apps.projekt` hängt von `apps.stunden` ab, nicht umgekehrt).

### Modell: `Stundensatz`

| Feld          | Typ                           | Beschreibung   |
| ------------- | ----------------------------- | -------------- |
| `jahr`        | PositiveIntegerField (unique) | Kalenderjahr   |
| `stundensatz` | MeasurementField (CHF)        | CHF pro Stunde |

- GeneralManager-Klasse mit `DatabaseInterface` und `AdditiveManagerPermission`.

### Validierungsregeln

| Regel                 | Fehlermeldung                                |
| --------------------- | -------------------------------------------- |
| `stundensatz > 0 CHF` | „Stundensatz muss grösser als 0 CHF/h sein." |

---

## Frontend

### Route: `/stundensaetze`

Zugang: nur Admin + Projektleiter.

#### Layout

```
[Logo]           [Projekte] [Stundensätze]      [Karl-Heinz]  [Abmelden]
────────────────────────────────────────────────────────────────────────────
Stundensätze

  Jahr    Stundensatz (CHF/h)
  ──────────────────────────────
  2026    95.00                  [Bearbeiten]
  2025    90.00                  [Bearbeiten]
  2024    87.00                  [Bearbeiten]

  [+ Neuer Stundensatz]
```

#### Verhalten

- Inline-Bearbeitung des CHF-Werts (Enter = speichern, Esc = abbrechen).
- „+ Neuer Stundensatz": Jahr + Betrag eingeben; Jahr muss eindeutig sein.
- Kein Löschen (Stundensätze sind historisch relevant).

---

## Out of Scope (vorerst)

- Automatischer Import aus Lohnbuchhaltung
- Mehr als ein Stundensatz pro Jahr (z. B. nach Mitarbeitertyp)
