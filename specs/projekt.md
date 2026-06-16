# Spec: Projektübersicht

## Ziel

Ablösung der bisherigen Excel-Datei durch eine digitale Projektübersicht in Forge.
Mittelfristig wird Bexio angebunden, um Ist-Daten automatisch zu beziehen.

---

## Begriffe

| Kürzel | Bedeutung                               |
| ------ | --------------------------------------- |
| WV     | Werksvertrag             |
| exkl.  | Exklusive Mehrwertsteuer |

---

## Benutzer & Rollen

| Rolle         | Login | Berechtigungen                                                                |
| ------------- | ----- | ----------------------------------------------------------------------------- |
| Admin         | Ja    | Vollzugriff + Benutzerverwaltung (Django Admin)                               |
| Projektleiter | Ja    | Projekte anlegen/bearbeiten, Soll/Ist-Werte eintragen, Stundensätze verwalten |
| Betrachter    | Ja    | Lesezugriff auf alles (für Inhaber/GF)                                        |
| Monteur       | Ja    | Nur Stunden-Ist bearbeiten; keine Finanzdaten sichtbar                        |

Kein anonymer Zugriff — jeder muss sich einloggen.

Konkrete Benutzer beim Start: 1× Admin, 2× Projektleiter (Simon, Karl-Heinz), 1× Betrachter (Inhaber), 2× Monteure.

---

## Backend

### App: `apps.projekt`

**Abhängigkeiten:** `apps.stunden` (für Stundensatz-Lookup bei Transport und Montage).

### Modell: `Projekt`

| Feld             | Typ                              | Beschreibung                                                                      |
| ---------------- | -------------------------------- | --------------------------------------------------------------------------------- |
| `name`           | CharField (max 200)              | Projektbezeichnung                                                                |
| `auftragsnummer` | CharField (max 50, unique)       | Eindeutige Nummer; dient auch als Bexio-Verknüpfungsschlüssel                     |
| `jahr`           | PositiveInteger                  | Das Jahr an dem das Projekt los geht, dient zur Ermittlung der Stunden            |
| `projektleiter`  | FK → User (nullable)             | Zugewiesener Projektleiter                                                        |
| `offerte_summe`  | MeasurementField (CHF)           | Erster Angebotsbetrag exkl. MwSt.                                                 |
| `wv_summe`       | MeasurementField (CHF, nullable) | Aktueller Werkvertragsumfang exkl. MwSt. — bei neuen Projekten noch nicht gesetzt |
| `auftrag_fertig` | BooleanField                     | Ob das Projekt abgeschlossen/archiviert werden kann                               |

**Berechnete Eigenschaft**
`summe_wv_plus`: WV-Summe (**TODO** das ist erstmal dasselbe, die implementierung kommt noch).
`ist_koste`: Summe aller Bexio Ist Kosten zu diesem Projekt
`ist_erloese`: Summe aller Bexio Ist Erlöse zu diesem Projet

> Ein Projekt kann zuerst in Forge oder zuerst in Bexio entstehen — beides ist möglich.
> Die `wv_summe` ist bei einem neuen Projekt noch nicht da

### Modell: `Kostenart`

ReadOnlyInterface vom general_manager

**Ertragsblock** (Zeilen oben in der Matrix, grau hinterlegt, nur Ist editierbar):

| Schlüssel  | Anzeigename |
| ---------- | ----------- |
| `regie`    | Regie       |
| `nachtrag` | Nachtrag    |

**Kostenblock** (Zeilen unten in der Matrix):

| Schlüssel                 | Anzeigename                           | Hinweis                                           |
| ------------------------- | ------------------------------------- | ------------------------------------------------- |
| `apparate`                | Apparate                              |                                                   |
| `kanaele_rohre`           | Kanäle und Rohre                      |                                                   |
| `armaturen`               | Armaturen                             |                                                   |
| `regulierung`             | Regulierung                           |                                                   |
| `schaltschrank`           | Schaltschrank                         |                                                   |
| `transport_montage`       | Transport und Montage                 | CHF = Stunden × Stundensatz des Jahres            |
| `stunden`                 | Stunden                               | Zeigt Anzahl Stunden, nicht CHF                   |
| `transport_montage_fremd` | Transport und Montage – Fremdleistung |                                                   |
| `isolation`               | Isolation                             |                                                   |
| `dienstleistung`          | Dienstleistung                        |                                                   |
| `diverses`                | Diverses                              |                                                   |
| `planung`                 | Planung                               |                                                   |
| `gemeinkosten`            | Gemeinkosten                          | Nur Ist-Spalte; kommt aus Bexio (rosa hinterlegt) |

> Das Mapping Bexio-Aufwandskonto → Kostenposition ist eindeutig (wird bei Bexio-Integration konfiguriert).
> Jeder Kategorie (`offerte`, `wv`, `ist`) enthält alle Kostenblöcke und Ertragsblöcke, allerdings Werden diese nur bei `offerte` manuell eingetragen übers Frontend. `wv` ist berechnet. `Ist` kommt über Bexio

### Modell: `KostenPosition`

Eine Zeile in der Projekt-Detailansicht. Pro Projekt existiert je eine Position pro `KostenArt` (unique_together).

| Feld               | Typ                              | Beschreibung               |
| ------------------ | -------------------------------- | -------------------------- |
| `projekt`          | FK → Projekt (CASCADE)           | Zugehöriges Projekt        |
| `art`              | FK → Kostenart                   | Zugehörige Art             |
| `offerte_position` | MeasurementField (CHF, nullable) | Manuell erfasster CHF-Wert |

### Validierungsregeln

| Regel                                 | Fehlermeldung                                |
| ------------------------------------- | -------------------------------------------- |
| `offerte_summe > 0 CHF`               | „Offerte-Summe muss grösser als 0 CHF sein." |
| `wv_summe > 0 CHF` (nur wenn gesetzt) | „WV-Summe muss grösser als 0 CHF sein."      |

### Berechnungsregeln (Backend)

**Soll offerte je Position:**
- `offerte_stunden` -> - `transport_montage` / `Stundensatz`
- alle anderen manuell

**Soll WV je Position (`wv_position`):**
- `stunden` → `offerte_stunden` (gleicher berechneter Wert wie Soll-Offerte, Ausnahme — kein separates Feld)
- `transport_montage` & `transport_montage_fremd` → `offerte_position` (bleibt gleich, Ausnahme)
- Weil `transport_montage` und `transport_montage_fremd` gleich bleiben ist die Formel bei `apparate`, `kanaele_rohre` und `armaturen` anders. Und zwar z.B. apparate:
definition `summe der drei` - `summe (offerte_position_prozent(je apparate, kanaele_rohre, armatur) * wv_summe`
definition `tmp_position` - `offerte_position_prozent(i.e. apparate) * wv_summe`
`tmp_position - ( Delta der Prozent von transport_montage * wv_summe ( tmp_position / summe der drei )  - ( Delta der Prozent von transport_montage_fremd * wv_summe ( tmp_position / summe der drei ) )`
- alle anderen → `offerte_position_prozent (siehe unten) * wv_summe`

**Ist Kosten je Position:**
- `ist_stunden` → Kommt über die Rückmeldung der Monteure (**TODO** wird noch in der specs/stunden.md kommen)
- `transport_montage` → `ist_stunden` × Jahres-Stundensatz (aus `apps.stunden`)
- Für alle anderen gilt, die Summe der Netto-Beträge der passenden Bexio-Lieferantenrechnungen
- **`None` wenn noch keine Rechnungen vorliegen** (leere Liste = kein Istwert, nicht `0 CHF`)

**Prozentuale Werte:**
- `offerte_position_prozent` = `offerte_position / offerte_summe × 100`
- `wv_position_prozent` = `wv_position / wv_summe × 100`
- `ist_position_prozent` = `ist_position / ist_koste × 100`

---

## Frontend

### Tech-Stack

| Bereich   | Entscheidung          |
| --------- | --------------------- |
| Framework | React 18 + TypeScript |
| Build     | Vite                  |
| Routing   | React Router v6       |
| Styling   | Tailwind CSS          |
| GraphQL   | Apollo Client         |
| State     | React Context + Hooks |

### Routen

```
/                    → Weiterleitung → /projekte
/login               → Login-Seite (alle Rollen)
/projekte            → Projektliste (alle eingeloggten Rollen)
/projekte/:id        → Projektdetail (alle eingeloggten Rollen; Monteur: eingeschränkte Ansicht)
/projekte/neu        → Neues Projekt (nur Admin + Projektleiter)
/stundensaetze       → Stundensatz-Verwaltung (→ specs/stunden.md)
```

Kein anonymer Zugriff. Alle Routen (außer `/login`) leiten unauthentifizierte Nutzer zu `/login` weiter.

### Benutzerrollen & Frontend-Berechtigungen

| Aktion                              | Monteur | Betrachter | Projektleiter | Admin                |
| ----------------------------------- | ------- | ---------- | ------------- | -------------------- |
| Login                               | ✓       | ✓          | ✓             | ✓                    |
| Projektliste (mit Finanzdaten)      | ✗       | ✓          | ✓             | ✓                    |
| Projektliste (nur Name/Auftragsnr.) | ✓       | –          | –             | –                    |
| Projektdetail (volle Matrix)        | ✗       | ✓          | ✓             | ✓                    |
| Projektdetail (nur Stunden-Zeile)   | ✓       | –          | –             | –                    |
| Projekt erstellen                   | ✗       | ✗          | ✓             | ✓                    |
| Soll/Ist-Werte bearbeiten           | ✗       | ✗          | ✓             | ✓                    |
| Stunden-Ist bearbeiten              | ✓       | ✗          | ✓             | ✓                    |
| Projekt archivieren                 | ✗       | ✗          | ✓             | ✓                    |
| Stundensätze verwalten              | ✗       | ✗          | ✓             | ✓                    |
| Benutzerverwaltung                  | ✗       | ✗          | ✗             | ✓ (via Django Admin) |

> Admin und Projektleiter haben aktuell die gleichen Rechte — Admin hat zusätzlich Zugang zur Benutzerverwaltung via Django Admin.

### Navigation / Header

```
[Logo]           [Projekte] [Stundensätze]      [Karl-Heinz]  [Abmelden]
```

- Links: Logo-Bild (`/logo.png`)
- Mitte: Navigationslinks (nur für eingeloggte Benutzer sichtbar); aktiver Link in `--forge-blue`, inaktive in `text-gray-500`
- Rechts: Benutzername + Abmelden (nur eingeloggt)
- Hintergrund: Weiß mit unterer Border (`border-b border-gray-200`)

### 1. Login-Seite (`/login`)

```
┌─────────────────────────────────┐
│           Forge                 │
│                                 │
│  Benutzername  [____________]   │
│  Passwort      [____________]   │
│                                 │
│            [Anmelden]           │
└─────────────────────────────────┘
```

- Fehler bei falschen Credentials: Inline-Fehlermeldung
- Nach Login: Weiterleitung zu `/projekte`

### 2. Projektliste (`/projekte`)

```
[Logo]           [Projekte] [Stundensätze]      [Karl-Heinz]  [Abmelden]
────────────────────────────────────────────────────────────────────────────
[+ Neues Projekt]   [☐ Archivierte anzeigen]

  Auftragsnr.   Name                    PL            WV exkl.    WV + Zusätze   Status
  ─────────────────────────────────────────────────────────────────────────────────────
  2022.0050     Hotel Glockenhof …      Karl-Heinz    319'220     393'319        Aktiv    [→]
  2022.0055     Raiffeisenbank …        Karl-Heinz    131'848     156'537        Fertig   [→]
```

- Sortierung per Klick auf Spaltenköpfe (Standard: Auftragsnummer aufsteigend)
- Archivierte Projekte (auftrag_fertig = true) standardmäßig ausgeblendet; Toggle zeigt sie ausgegraut
- Monteur: sieht nur Auftragsnr., Name, Status (keine Finanzdaten)

### 3. Projektdetail (`/projekte/:id`)

#### Kopfbereich

```
[← Zurück]                                          [Bearbeiten]  [Archivieren]

Hotel Glockenhof Sihlstr, ZH
Auftragsnummer: 2022.0050   |   PL: Karl-Heinz Bauer
1. Offerte exkl.: 365'595.00   |   Summe WV exkl.: 319'220.06   |   Summe WV + Zusätze: 393'319.37
Auftrag fertig: Nein
```

„Bearbeiten" und „Archivieren" nur für Projektleiter + Admin.
Button „Bearbeiten" → Kopffelder werden zu Eingabefeldern (kein Modal).

#### Kostenmatrix

```
                        │  Soll Offerte       │  Soll WV            │  Ist
                        │  %        CHF       │  %        CHF       │  CHF          %
────────────────────────┼─────────────────────┼─────────────────────┼──────────────────
Regie              [G]  │                     │                     │  1'790.00
...
════════════════════════╪═════════════════════╪═════════════════════╪══════════════════
Apparate                │  65%   238'275.00   │  64%   205'395.02   │  123'591.81   60%  🟢
...
Stunden                 │          289.66 h   │          289.66 h   │      247.50 h  85%
...
════════════════════════╪═════════════════════╪═════════════════════╪══════════════════
Summe der Kosten   [C]  │ 100%   365'595.00   │ 100%   319'220.06   │  265'844.78   83%
────────────────────────┼─────────────────────┼─────────────────────┼──────────────────
Gewinn / Verlust        │  0.00               │  0.00               │  127'474.59   40%  🟡
Differenz WV–Off.       │ -15%                │ -46'374.94          │
────────────────────────┼─────────────────────┼─────────────────────┼──────────────────
Bisher verr. Total      │                     │                     │  362'978.16
Abgrenzung              │                     │                     │   97'133.38  113.71%
Vorrat                  │                     │                     │  -43'758.10
```

Legende: **[G]** `bg-gray-50` (Ertragsblock) · **[P]** `bg-gray-50` (Gemeinkosten) · **[C]** `bg-gray-100` (Summe)

#### Farbcodierung (Ist-Spalte, %-Wert)

| Bedingung              | Farbe           |
| ---------------------- | --------------- |
| Ist % < 100 %          | 🟢 Grün          |
| Ist % >= 100 %         | 🟡 Orange        |
| Gewinn/Verlust positiv | Gelb hinterlegt |
| Gewinn/Verlust negativ | Rot hinterlegt  |

#### Inline-Bearbeitung

Nur für Projektleiter + Admin. Klick auf editierbare Zelle → `<input>`. Enter = speichern, Esc = verwerfen.

| Position                             | Soll Offerte  | Soll WV                         | Ist           |
| ------------------------------------ | ------------- | ------------------------------- | ------------- |
| Ertragsblock (Regie, Nachtrag)        | ✗             | ✗                               | ✓             |
| Kostenblock (Apparate, Kanäle, …)    | ✓             | ✗ (berechnet)                   | ✗ (berechnet) |
| Transport und Montage                | ✓             | ✗ (berechnet)                   | ✗ (berechnet) |
| Stunden                              | ✗ (berechnet) | ✗ (berechnet = offerte_stunden) | ✗ (berechnet) |
| Gemeinkosten                         | ✗             | ✗                               | ✗ (berechnet) |

### 4. Neues Projekt (`/projekte/neu`)

| Feld                   | Pflicht                 |
| ---------------------- | ----------------------- |
| Name                   | Ja                      |
| Auftragsnummer         | Ja (Uniqueness-Prüfung) |
| Projektleiter          | Nein (Dropdown)         |
| 1. Offerte exkl. (CHF) | Ja                      |
| Summe WV exkl. (CHF)   | Ja                      |

Nach Anlegen: Weiterleitung zur Detailansicht.

### Zahlenformat

- CHF: Schweizer Apostroph-Trennzeichen: `365'595.00`
- Prozent: `65 %` (bei Abgrenzung: `113.71 %`)
- Stunden: `289.66 h`
- Negative Werte: Minuszeichen + rote Schrift

---

## Bexio-Integration (spätere Phase)

- Anbindung via Bexio API
- Kreditorenrechnungen → eindeutiges Mapping auf Kostenpositionen
- Ist-Daten und Gemeinkosten werden automatisch gezogen

---

## Out of Scope (vorerst)

- Mitarbeiterstunden-Modul (Stunden je Projekt aus DB)
- Bexio-Live-Sync
- Mobile-/Responsive-Ansicht
- Dark Mode
- Export (PDF, Excel)
- Suche / Filterung in der Projektliste
- Benutzerverwaltung im Frontend (→ Django Admin)
