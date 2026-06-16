# ADR 005 – Frontend-Design-Workflow via claude.ai/design

**Datum:** 2026-05-22
**Status:** Akzeptiert

## Kontext

Für die visuelle Gestaltung neuer UI-Seiten und Komponenten brauchen wir einen klaren Workflow, der Design-Entscheidungen von der technischen Implementierung trennt. claude.ai und Claude Code (dieses CLI) sind separate Umgebungen ohne direkte Verbindung.

## Entscheidung

Designs werden auf **claude.ai/design** (Artifacts/Canvas) erarbeitet. Die Ergebnisse werden als strukturierter **Handoff** in `specs/designs/` abgelegt und dort von Claude Code implementiert.

## Workflow

1. **Design auf claude.ai/design** — Mockups, Wireframes oder Komponenten als HTML/CSS/React-Artefakte erstellen. Corporate Design (Tokens, Patterns) aus `docs/skills/frontend-design/SKILL.md` als Kontext mitgeben.
2. **Handoff ablegen** — Strukturierter Ordner `specs/designs/` mit folgenden Dateien:
   - `README.md` — Überblick, Kontext, globale Akzeptanzkriterien, Lesereihenfolge
   - `design-system.md` — Farben, Typografie, Zahlen-Formatter, Status-Definitionen
   - `shared-components.md` — geteilte Komponenten (Navbar, Icons etc.)
   - Eine Datei pro Seite, z.B. `projektdetail.md`, `projektuebersicht.md`
3. **Implementierung** — Claude Code liest zuerst `README.md`, dann `design-system.md` + `shared-components.md`, dann die jeweilige Seiten-Datei.
4. **Visual-Feedback / Korrekturen** — Screenshots für Vergleiche in `specs/designs/compare_img/` ablegen (`current.png` + `target.png`). Claude Code liest beide Bilder und fixiert Abweichungen direkt.

## Begründung

- Klare Trennung: Design-Iteration auf claude.ai, saubere Implementierung hier.
- Kein Extra-Tool (Figma) nötig.
- Modulare Struktur (System / Shared / Seite) vermeidet Duplizierung und macht partielle Updates einfach.

## Konsequenzen

- Beim Handoff immer `docs/skills/frontend-design/SKILL.md` als Kontext auf claude.ai mitgeben, damit Tokens und Patterns korrekt verwendet werden.
- Divergenzen zwischen Mockup und tatsächlichem Tech-Stack (z.B. Tailwind-Klassen statt inline-Styles) werden bei der Implementierung still korrigiert.
- Handoff-Dateien sind Referenz, kein produktionsreifer Code — Claude Code baut nach dem bestehenden Codebase-Pattern.
