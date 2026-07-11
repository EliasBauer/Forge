---
name: frontend
description: Konventionen, Stack und Design-Tokens für das Forge-Frontend. Nutze diese Skill bei jeder Frontend-Arbeit in Forge — React/TypeScript-Komponenten, Styling und Design-Tokens, Apollo/GraphQL-Anbindung, Vite, Frontend-Tests. Superpowers deckt Frontend NICHT ab; diese Skill trägt das Forge-Spezifische.
---

# Forge Frontend

## Architektur-Regeln (nicht verhandelbar)

- Frontend macht KEINE Validierung, keine Permission-Checks, keine Zugriffslogik — das gehört ins Backend (GM / Permissions).
- Frontend-Aufgaben: Routing, Darstellung, User-Input, GraphQL (Queries / Mutations / Subscriptions), WebSockets, Server-Fehler anzeigen.

## Stack

- React + TypeScript, Build/Dev über Vite (Ordner `frontend/`).
- Apollo Client gegen `/graphql/` (HttpLink); der Vite-Proxy leitet `/graphql` auf `http://localhost:8000`.
- Im Container muss Vite mit `--host` laufen, sonst kein Zugriff: `npm run dev -- --host`.
- Styling: Tailwind v4 (`@import "tailwindcss"`). Tests: vitest (`npm --prefix frontend test`).

## GraphQL aus Frontend-Sicht (Autogen-Fallen)

Das Schema wird vom GeneralManager generiert (Details: `general-manager`-Skill, §9):

- Felder sind **camelCase**: `istWertList`, `offerteSumme`.
- **ForeignKey = String** (str() des Objekts) — keine Sub-Selection; `projektleiter { name }` schlägt fehl.
- **Measurement**: Output `{ value unit }`; Input als **String** `"50000 CHF"`.
- **Float / Decimal**: als Zahl senden; deutsche Komma-Eingabe vorher umwandeln: `parseFloat(val.replace(",", "."))`.
- Mutation-Rückgabefeld = Klassenname mit Großbuchstabe: `createProjekt { Projekt { id } }`.
- Listen: `{ items { ... } pageInfo { totalCount } }` (nicht `results`).

## Design-Tokens

**Single Source of Truth:** `frontend/src/index.css` (Tailwind v4, Tokens als CSS-Variablen unter `:root`). Die Datei ist für Namen *und* Werte maßgeblich — nie Hex/px hartkodieren, immer den Token nehmen; neue Werte zuerst dort anlegen, dann referenzieren.

Token-Vokabular (`--forge-*`, Werte in der Datei):

- Marke: `--forge-dark`, `--forge-blue` (+ `--forge-blue-soft`, `--forge-blue-hover`), `--forge-red` (+ `--forge-red-soft`)
- Navigation: `--forge-nav-text`, `--forge-nav-muted`, `--forge-nav-active`
- Fläche: `--forge-bg`

Konsum in Komponenten: über `var(--forge-blue)` bzw. als Tailwind-Arbitrary-Value `bg-[var(--forge-blue)]`. (Für echte Utility-Klassen wie `bg-forge-blue` müssten die Tokens in einen `@theme`-Block statt `:root`.)

Asset: Logo unter `frontend/public/compressed_logo_jane.webp`.