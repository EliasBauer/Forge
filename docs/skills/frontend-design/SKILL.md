# Frontend-Design

> Skill für die Erstellung von UI-Komponenten und Seiten im Forge-Projekt.
> Tech-Stack: React, TypeScript, Tailwind CSS 4, Vite.

---

## Wann diesen Skill nutzen

- Neue Seiten oder Komponenten bauen
- Bestehendes UI überarbeiten oder stylen
- Dashboard-Views, Formulare, Listen, Detail-Ansichten

---

## Tech-Stack & Constraints

- **Framework:** React 18 + TypeScript
- **Styling:** Tailwind CSS 4 (Utility-First, keine separaten CSS-Dateien)
- **Bundler:** Vite 8
- **Router:** react-router-dom v7
- **API:** Apollo Client 4 (GraphQL via `HttpLink`, Endpunkt `/graphql/`)
- **Auth:** REST-basiert (`/api/login/`, `/api/logout/`, `/api/me/`) via `AuthContext`
- **Reaktiv:** "Zustand" vorhanden (für komplexe asynchrone Logik)
- **Icons:** Noch nicht festgelegt (Vorschlag: lucide-react)
- **Animationen:** CSS-Transitions bevorzugen, nur bei Bedarf Motion-Library

---

## Corporate Design

CSS-Variablen definiert in `frontend/src/index.css`:

### Kern-Tokens

| Token         | Wert      | Verwendung                               |
| ------------- | --------- | ---------------------------------------- |
| `--forge-dark` | `#1E1E1E` | Footer, dunkle Flächen                   |
| `--forge-blue` | `#4A6CF7` | Primäre Aktionen, Links, aktive Elemente |
| `--forge-red`  | `#D93036` | Warnungen, Fehler, destruktive Aktionen  |

### Erweiterte Tokens

| Token               | Wert      | Verwendung                                  |
| ------------------- | --------- | ------------------------------------------- |
| `--forge-bg`         | `#F8F9FB` | Seiten-Hintergrund                          |
| `--forge-blue-soft`  | `#E8ECFE` | Badge-/Tag-Hintergrund, Selection-Highlight |
| `--forge-blue-hover` | `#3B5CE5` | Hover/Active-State für Blue-Buttons/-Links  |
| `--forge-red-soft`   | `#FDE8E9` | Fehler-Hintergrund, Warn-Banner             |
| `--forge-nav-text`   | `#FFFFFF` | (reserviert, derzeit nicht genutzt)         |
| `--forge-nav-muted`  | `#A8A8A8` | (reserviert, derzeit nicht genutzt)         |
| `--forge-nav-active` | `#7B93FF` | (reserviert, derzeit nicht genutzt)         |

In Tailwind-Klassen über `style={{ color: "var(--forge-blue)" }}` oder direkt als CSS-Variable nutzen.

### Farbregeln

- Hintergrund: `var(--forge-bg)` (`#F8F9FB`) für Seiten / Weiß für Karten, Formulare, Inline-Editing
- Text: Standard Tailwind-Graustufen (`text-gray-700`, `text-gray-900` etc.)
- **Navbar:** Weißer Hintergrund (`bg-white`), untere Border (`border-b border-gray-200`). Aktive Links: `--forge-blue`. Inaktive Links: `text-gray-500`. Username und Abmelden: `text-gray-700` / `text-gray-400`.
- Primäre Aktionen (Buttons, Links): `--forge-blue`, Hover: `--forge-blue-hover`
- Destruktive Aktionen: `--forge-red-soft` als Hintergrund + `--forge-red` als Text — nie `--forge-red` als großflächigen Hintergrund
- Badges und Tags: `--forge-blue-soft` / `--forge-red-soft` als Hintergrund mit der jeweiligen Kern-Farbe als Text
- Sparsam mit Farbe — das Design soll professionell und ruhig wirken, nicht bunt. Lieber ein kräftiges Blau selten einsetzen als ein blasses überall.

### WCAG-Kontraste (alle ≥ 4.5:1 für AA)

| Kombination                  | Ratio |
| ---------------------------- | ----- |
| `--forge-blue` auf `#FFFFFF`  | 4.8:1 |
| `--forge-red` auf `#FFFFFF`   | 5.1:1 |
| `text-gray-500` auf `#FFFFFF`| 4.6:1 |

---

## Design-Prinzipien

### Allgemein

- **Klarheit vor Kreativität.** Forge ist ein Business-Tool für Handwerker, kein Portfolio-Stück. Die UI muss auf den ersten Blick verständlich sein.
- **Konsistenz.** Gleiche Patterns für gleiche Probleme. Eine Liste sieht immer gleich aus, egal ob Projekte oder Stundensätze.
- **Dichte wo nötig.** Dashboards dürfen kompakt sein. Formulare brauchen Luft.
- **Mobile-Awareness.** Kein Mobile-First, aber Layouts sollen auf Tablets nicht brechen (Monteure nutzen eventuell Tablets in Phase 2).

### Typografie

- System-Font-Stack über Tailwind (`font-sans`). Kein Custom-Font nötig — Geschwindigkeit und Einfachheit gehen vor.
- Klare Hierarchie: Eine Überschrift pro Seite, Subheadings für Sektionen, Body-Text für Inhalte.
- Zahlen in Tabellen monospaced (`tabular-nums` via Tailwind).

### Layout

- Max-Width Container für Content (`max-w-7xl mx-auto`)
- Sidebar-Navigation (später, wenn mehr als 3 Seiten)
- Responsive Grid für Karten/Dashboard-Elemente
- Ausreichend Whitespace — nicht alles vollpacken
- Responsive Design, auch für Desktop-, Handy- und Tablet-Nutzung optimieren

### Komponenten-Patterns

- **Tabellen:** Für Listen (Projekte, Stundensätze). Sortierbar, mit klaren Headers.
- **Karten:** Für Dashboard-KPIs (Gewinn/Verlust-Übersicht).
- **Formulare:** Labels über den Feldern. Validierungsfehler inline unter dem Feld in Rot.
- **Buttons:** Primary (blau), Destructive (rot), Secondary (grau/outline). Klar unterscheidbar.
- **Loading States:** Skeleton-Loader oder Spinner. Keine leeren Seiten.
- **Empty States:** Hilfreiche Nachricht + Aktion ("Noch keine Projekte. Jetzt anlegen.")

---

## Datei-Struktur

```
frontend/src/
├── components/           # Wiederverwendbare UI-Komponenten
│   ├── Layout.tsx        # Navbar + Page-Wrapper
│   ├── ProtectedRoute.tsx # Auth-Guard mit optionalem allowedGroups
│   └── ...
├── contexts/             # React Contexts
│   └── AuthContext.tsx   # Auth-State, useAuth(), AuthProvider
├── graphql/          # GraphQL-Queries und Mutations
│   ├── queries.ts
│   ├── mutations.ts
│   └── subscriptions.ts
├── pages/                # Seitenkomponenten (eine pro Route)
│   ├── LoginPage.tsx
│   ├── ProjektListePage.tsx
│   ├── ProjektDetailPage.tsx
│   ├── ProjektNeuPage.tsx
│   └── StundensaetzePage.tsx
├── lib/                  # Apollo Client
│   └── apolloClient.ts
├── utils/                # Pure Hilfsfunktionen
│   ├── format.ts         # chf(), pct(), GQLMeasurement
│   └── permissions.ts    # canEdit(), canViewFinancials(), ...
├── test/
│   └── setup.ts          # Vitest-Setup (@testing-library/jest-dom)
├── App.tsx               # Router-Konfiguration
├── main.tsx
└── index.css             # Tailwind-Import + CSS-Variablen
```

---

## Auth & Permissions

### AuthContext (`contexts/AuthContext.tsx`)

- `AuthProvider` wrapping in `App.tsx` — immer vorhanden
- `useAuth()` liefert `{ user, loading, login, logout }`
- `AuthUser` hat `id`, `username`, `groups: UserGroup[]`, `isStaff`
- `UserGroup`: `"Admin" | "Projektleiter" | "Betrachter" | "Monteur"`
- Login/Logout via REST (`/api/login/`, `/api/logout/`), Session via `/api/me/`

### ProtectedRoute (`components/ProtectedRoute.tsx`)

```tsx
// Nur eingeloggte Nutzer
<ProtectedRoute>...</ProtectedRoute>

// Nur bestimmte Gruppen (sonst Redirect zu /projekte)
<ProtectedRoute allowedGroups={["Admin", "Projektleiter"]}>...</ProtectedRoute>
```

### Permissions-Helfer (`utils/permissions.ts`)

| Funktion                       | Erlaubt              |
| ------------------------------ | -------------------- |
| `canEdit(user)`                | Admin, Projektleiter |
| `canViewFinancials(user)`      | alle außer Monteur   |
| `canManageStundensaetze(user)` | Admin, Projektleiter |
| `canCreateProject(user)`       | Admin, Projektleiter |

**Wichtig:** Permissions-Checks nur in Komponenten für UI-Sichtbarkeit. Keine Zugriffskontrolle im Frontend — das ist Aufgabe des Backends.

### Format-Helfer (`utils/format.ts`)

```ts
import { chf, pct } from "../utils/format";

chf({ value: 1500, unit: "CHF" }); // "CHF 1'500.00"
chf(1500); // "CHF 1'500.00"
chf(null); // "–"
pct(12.5); // "12.5 %"
```

`GQLMeasurement = { value: number; unit: string }` — der Typ für Measurement-Felder aus GraphQL.

---

## Design-Workflow (claude.ai/design → Claude Code)

Neue Seiten und Komponenten werden zuerst auf **claude.ai/design** als Mockup erarbeitet, bevor sie hier implementiert werden.

1. **Auf claude.ai/design:** Mockup als Artefakt erstellen. Dieses Dokument (`SKILL.md`) als Kontext mitgeben, damit Tokens und Patterns stimmen.
2. **Handoff ablegen:** Strukturierter Ordner `specs/designs/` mit folgenden Dateien:
   - `README.md` — Überblick, Kontext, globale Akzeptanzkriterien, Lesereihenfolge
   - `design-system.md` — Farben, Typografie, Zahlen-Formatter, Status-Definitionen
   - `shared-components.md` — geteilte Komponenten (Navbar, Icons etc.)
   - Eine Datei pro Seite, z.B. `projektdetail.md`, `projektuebersicht.md`
3. **Implementierung:** Claude Code liest zuerst `README.md`, dann `design-system.md` + `shared-components.md`, dann die jeweilige Seiten-Datei und setzt alles in React + Tailwind um (Abweichungen vom Mockup werden still korrigiert).
4. **Visual-Feedback:** Screenshots für Vergleiche in `specs/designs/compare_img/` ablegen (`current.png` + `target.png`). Claude Code liest beide und fixiert Abweichungen direkt.

Hintergrund: [ADR 005](../../adr/005-frontend-design-workflow-claude-ai.md)

---

## Vorgehen bei neuen Komponenten

1. **Prüfen:** Gibt es schon eine ähnliche Komponente? Wiederverwenden statt neu bauen.
2. **Props definieren:** TypeScript-Interface für Props, keine `any`-Typen.
3. **Tailwind nutzen:** Styling über Utility-Klassen, keine inline-Styles, kein separates CSS.
4. **States abdecken:** Loading, Empty, Error, Success — nicht nur den Happy Path.
5. **Testen:** Mindestens ein Render-Test mit `@testing-library/react`.

---

## Anti-Patterns (vermeiden)

- Keine `className`-Strings die länger als eine Zeile sind → in Variablen auslagern oder Komponente extrahieren
- Keine Business-Logik in Komponenten → GraphQL-Queries in eigene Hooks auslagern
- Keine hardcodierten Farben → Tailwind-Klassen oder CSS-Variablen nutzen
- Keine `console.log` im finalen Code
- Keine unbenutzten Imports oder Variablen (ESLint fängt das ab)
