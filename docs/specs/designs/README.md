# Forge – Build-Anweisung für Claude Code

Interne Projektcontrolling-Web-App **Forge** für Handwerksbetriebe mit Bexio-Integration.
Diese Doku beschreibt die vier Seiten der App in einer Form, die ein Engineering-Team
(oder Claude Code) direkt in produktionsreifen Code übersetzen kann.

## Aufbau dieser Doku

Lies in dieser Reihenfolge:

| #   | Datei                                            | Was drinsteht                                                                                           |
| --- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| 1   | [`design-system.md`](./design-system.md)         | Farben, Typografie, Zahlen-Formatter, Vorzeichen-Konvention, Status-Definitionen, Abweichungs-Schwellen |
| 2   | [`shared-components.md`](./shared-components.md) | `<Navbar>`, Logo, Icon-Set — von allen Seiten verwendet                                                 |
| 3   | [`projektuebersicht.md`](./projektuebersicht.md) | **Seite 1**: Liste aller Projekte (`/projekte`)                                                         |
| 4   | [`projektdetail.md`](./projektdetail.md)         | **Seite 2**: Kostenpositionen + Visualisierung (`/projekte/:id`)                                        |
| 5   | [`stundensaetze.md`](./stundensaetze.md)         | **Seite 3**: Stundensätze pro Jahr (`/stundensaetze`)                                                   |
| 6   | [`todo.md`](./aufgaben.md)                       | **Seite 4**: Offene-Punkte-Dashboard (`/todo`)                                                          |

Zuerst Design-System und Shared-Components lesen, dann die Seiten-Docs — die
Seiten verweisen auf die geteilten Konzepte, statt sie zu duplizieren.

---

## Kontext

- **Anwendung**: Browser-only Single-Page-App (interne Büro-Anwendung, kein Mobile).
- **ERP-Anbindung**: Ist-Kosten und Ausgangsrechnungen kommen aus einem ERP-System;
  alle ERP-Werte sind read-only und visuell als solche markiert (blauer Tint).
- **Sprache**: Deutsch (Schweizer Hochdeutsch). Zahlen Schweizer Format: `CHF 12'345.00`.
- **Stack-Empfehlung**: React + TypeScript, Tailwind CSS, Vite. Routing via React Router.
  (Der Prototyp ist React + Babel-Standalone + Tailwind-CDN — produktionsmässig auf Vite umstellen.)
- **Viewport**: Desktop ≥ 1280 px. Kein Mobile-Responsive im aktuellen Scope.

## Navigation (Routen)

| Route            | Seite            | Tab in Navbar |
| ---------------- | ---------------- | ------------- |
| `/projekte`      | Projektübersicht | Projekte      |
| `/projekte/:id`  | Projektdetail    | Projekte      |
| `/stundensaetze` | Stundensätze     | Stundensätze  |
| `/todo`          | Todo             | Todo          |

Tab-Reihenfolge in der Navbar: **Projekte → Stundensätze → Todo**.

Verlinkungen zwischen den Seiten:
- Projektübersicht-Zeile → Projektdetail
- Projektdetail-Breadcrumb → Projektübersicht
- Todo-Eintrag „Fehlende Stundensätze" → Stundensätze
- Stundensätze-Hinweis → Todo

## Globale Akzeptanzkriterien

Gelten für alle Seiten:

- [ ] Schweizer Zahlenformat überall, auch in Inputs (Apostroph-Tausender)
- [ ] Negative CHF-Werte mit U+2212 und U+202F (kein klebendes `-`)
- [ ] Alle Geld- und Prozent-Spalten mit `tabular-nums` (Ziffern fluchten)
- [ ] Sticky-Layer-Stacking: Navbar `top:0`, Table-Header `top:56px`
- [ ] Alle Backend-Calls als typisierte API-Aufrufe (kein implizites `any`)
- [ ] Keine ungenutzten Status — nur `active` und `archived` (siehe Design-System)
- [ ] Logo: bestehendes Forge-Asset unter `assets/brand/` verwenden (siehe Shared-Components)

## Out of Scope

Bewusst **nicht** Teil dieses Builds — bitte nicht spekulativ implementieren:

- Filter (außer der beschriebenen Textsuche) und Pagination in der Projektübersicht
- Summenzeile / Aggregat über alle Projekte
- Mehrstufige Status („In Verzug", „Abgeschlossen" — der operative Zustand
  ergibt sich aus der Kostenheatmap, nicht aus einem Label)
- Modale „Neues Projekt anlegen" / „Projekt bearbeiten" — Buttons sind da, Action TBD
- Mobile Responsive
- Speaker-Notes / Print-View

## Referenz-Prototyp

Im Prototyp-Projekt-Root liegen die finalen interaktiven Versionen:

```
Projektuebersicht.html       ← Seite 1
Projektdetail.html           ← Seite 2
Stundensaetze.html           ← Seite 3
Todo.html                    ← Seite 4
shared/base.css
shared/icons.jsx
shared/formatters.jsx
shared/Navbar.jsx
assets/brand/forge-logo.svg  ← NUR Vorschau-Fallback, siehe shared-components.md
```

Bei Unklarheit zu Pixel-Details, Mikro-Interaktionen oder Spacing: HTML im Browser
öffnen und Devtools nutzen. Die Mock-Daten in den Files entsprechen den Beispielwerten
in den Seiten-Docs.
