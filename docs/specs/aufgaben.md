# Spec: Aufgaben – Onboarding-Hilfestellung

## Ziel

Eine neue Seite „Aufgaben" (Route `/aufgaben`) zeigt dem Nutzer, was in der
Applikation noch fehlt, um vollständig zu sein. Damit wird der Nutzer schrittweise
geführt, die App korrekt zu befüllen.

---

## Akzeptanzkriterien

1. Nav-Reihenfolge: Projekte | Stundensätze | **Aufgaben**
2. `/aufgaben` ist für alle authentifizierten User zugänglich.
3. Sektion „Stundensatz" listet nur Jahre auf, die in mindestens einem Projekt
   vorkommen, aber keinen Stundensatz haben.
4. Ist die Sektion leer, erscheint „Alles vollständig" als positives Feedback.

---

## Backend – `AufgabenStundensatz`

```python
# apps/stunden/calculation_manager/aufgaben_stundensatz.py
class AufgabenStundensatz(GeneralManager):
    class Interface(CalculationInterface):
        pass  # Singleton-Zugriff

    @graph_ql_property
    def fehlende_stundensatz_jahre(self) -> list[int]:
        jahre_projekte = {p.jahr for p in Projekt.filter()}
        jahre_stundensatz = {s.jahr for s in Stundensatz.filter()}
        return sorted(jahre_projekte - jahre_stundensatz)
```

---

## GraphQL-Schema (auto-generiert)

```graphql
query GetFehlendeStundensatzJahre {
  aufgabenstundensatz {
    fehlende_stundensatz_jahre
  }
}
```

---

## Frontend – `AufgabenPage.tsx`

### Route & Nav

- Route: `/aufgaben` (ProtectedRoute, keine allowedGroups-Einschränkung)
- Default-Redirect `/` → `/projekte`
- Nav-Link: `Aufgaben` → `/aufgaben` (erster Eintrag, vor Projekte)

### Darstellung

```
Aufgaben

── Stundensätze ─────────────────────
  2024
  2025
```

Leerzustand: grüner Text „Alles vollständig".

---

## Nicht im Scope

- Projekte mit fehlenden Kontopositionen (entfernt – `fehlende_kontoposition` nicht mehr im Backend)
- Direktverlinkung zu Edit-Seiten (Future)
- Weitere Checks außer Stundensatz (Future)
- Schreiboperationen
