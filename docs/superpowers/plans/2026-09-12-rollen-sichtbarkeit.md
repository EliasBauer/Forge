# Rollenabhängige Sichtbarkeit von Finanzdaten — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Betrachter sehen keine einzelnen Kostenpositionen und kein Diagramm, Monteure sehen die Projektliste ohne Finanzspalten und kommen nicht in die Projektdetails — durchgesetzt im Backend über GM-Permissions, im Frontend nur abgebildet.

**Architecture:** Die Permission-Klassen der vier betroffenen Manager (`Projekt`, `KostenPosition`, `IstWert`, `ProjektKennzahlen`) sind die einzige Quelle der Wahrheit. `CalculationPermission` wertet `__read__` statisch aus und liefert Unberechtigten `deny_all` (schließt eine bestehende Lücke, über die Finanzkennzahlen sogar anonym lesbar waren). Die globalen Capabilities `canViewFinanzen` und `canViewKostenPositionen` werden aus genau diesen Permission-Klassen abgeleitet statt aus Gruppennamen, sodass Frontend-Anzeige und Backend-Antwort nicht auseinanderlaufen können.

**Tech Stack:** Python 3.12, Django, GeneralManager 0.79.3, GraphQL (graphene), pytest + pytest-django; React 18 + TypeScript, Apollo Client 4, react-router-dom 7, vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-09-12-rollen-sichtbarkeit-design.md`

## Global Constraints

- Alle Befehle laufen **direkt** in diesem Container (diese Session läuft bereits im Devcontainer) — kein `devcontainer exec`-Präfix.
- Backend-Tests: `uv run --group dev pytest <pfad>`. Frontend-Tests: `npm --prefix frontend test`.
- Das volle Gate ist `pre-commit run --all-files` (ruff, pytest, mypy, vitest). „Erledigt" gilt erst, wenn es grün ist.
- **Coverage-Gate: 100 %** (`fail-under=100`). Jeder neue Code-Zweig braucht einen Test. Einzelne Test-Dateien deshalb mit `--no-cov` laufen lassen; das Gate prüft die Gesamtsuite.
- mypy läuft mit `strict = true` und `warn_unreachable = true`.
- ruff: `line-length = 88`, Regeln `E, F, I, B`.
- **Niemals `git commit --no-verify`.**
- Bei jedem Task-Commit diese Plan-Datei mit in `git add` aufnehmen, damit die abgehakten Boxen mitcommittet werden.
- Commit-Messages enden mit:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01VBU5FCdLVkYdtv9ThCqJdQ
  ```
- GM-Regel: Feldzugriff immer via `self.feldname`, Related-Lookups über den GM (`KostenPosition.filter(projekt=...)`), nie über rohes ORM.
- Frontend-Regel: keine Validierung, keine Permission-Logik, keine Zugriffslogik — nur Darstellung anhand der vom Server gelieferten Capabilities.

## Dateiübersicht

| Datei | Verantwortung | Task |
|---|---|---|
| `src/apps/authentication/permission.py` | `CalculationPermission` wertet `__read__` statisch aus | 1 |
| `src/apps/projekt/calculation_manager/ist_wert.py` | eigenes `__read__` (Admin, Projektleiter) | 1 |
| `src/apps/projekt/calculation_manager/projekt_kennzahlen.py` | eigenes `__read__` (+ Betrachter) | 1 |
| `src/apps/projekt/tests/test_permissions_graphql.py` | **neu** — Rollen-Matrix gegen `/graphql/` | 1, 2 |
| `src/apps/projekt/models/projekt.py` | `isMonteur` im `__read__`, Attribut-Regeln auf den Summen | 2 |
| `src/apps/projekt/models/kosten_position.py` | eigenes `__read__` (Admin, Projektleiter) | 2 |
| `src/apps/authentication/graphql_capabilities.py` | Capabilities aus Permissions ableiten, `canViewKostenPositionen` | 3 |
| `src/apps/authentication/tests/test_authentication.py` | Read-Plan-Unit-Tests + erweiterte Capability-Matrix | 1, 3 |
| `frontend/src/contexts/AuthContext.tsx` | `canViewKostenPositionen` im Capability-Typ | 4 |
| `frontend/src/graphql/queries.ts` | `ME` fragt die neue Capability ab | 4 |
| `frontend/src/App.tsx` | Route `/projekte/:id` hinter `canViewFinanzen` | 4 |
| `frontend/src/pages/ProjektListePage.tsx` | Zeilen-Navigation nur mit `canViewFinanzen` | 4 |
| `frontend/src/pages/ProjektDetailPage.tsx` | Positionszeilen/Legende/Diagramm an `canViewKostenPositionen` | 5 |
| `CONTEXT.md`, `.claude/skills/general-manager/references/reference.md` | Rollen- und GM-Doku nachziehen | 6 |

## Vorab verifizierte GM-Mechanik

Diese Punkte wurden während des Designs mit Wegwerf-Probes gegen `/graphql/` bestätigt — darauf darf sich der Umsetzende verlassen:

- `ReadPermissionPlan(filters=[], requires_instance_check=False, decision="deny_all")` auf einem `CalculationInterface`-Manager liefert `items: []`, sowohl bei der Top-Level-Query als auch verschachtelt.
- Eine Attribut-Regel `offerte_summe = {"read": [...]}` auf `Projekt` lässt die Zeile sichtbar und liefert nur das Feld als `null` — kein GraphQL-Fehler.
- `__based_on__ = "projekt"` allein schränkt `KostenPosition` **nicht** ein, sobald `Projekt` lesbar ist; das explizite `__read__` in Task 2 ist deshalb nötig.
- `Manager.Permission(Manager, user)` funktioniert im Klassen-Kontext inklusive `__based_on__`-Delegation; `GeneralManager.Permission` ist als `Type[BasePermission]` deklariert, mypy akzeptiert den Aufruf.

---

### Task 1: Calculation-Manager gegen unberechtigte Lesezugriffe absichern

Schließt die Sicherheitslücke: `projektKennzahlenList` und `istWertList` sind aktuell für **jeden** lesbar, auch anonym.

**Files:**
- Modify: `src/apps/authentication/permission.py:49-61`
- Modify: `src/apps/projekt/calculation_manager/ist_wert.py:24`
- Modify: `src/apps/projekt/calculation_manager/projekt_kennzahlen.py:22`
- Create: `src/apps/projekt/tests/test_permissions_graphql.py`
- Modify: `src/apps/authentication/tests/test_authentication.py` (Read-Plan-Unit-Tests anhängen)

**Interfaces:**
- Consumes: nichts aus früheren Tasks.
- Produces:
  - `CalculationPermission.get_read_permission_plan(self) -> ReadPermissionPlan` — liefert `decision="deny_all"` wenn `check_operation_permission("read")` False ist, sonst `filters=[{"filter": {}, "exclude": {}}]` mit `requires_instance_check=False`.
  - `IstWert.Permission` und `ProjektKennzahlen.Permission` als innere Klassen (Subklassen von `CalculationPermission`) mit eigenem `__read__`.
  - Test-Basisklasse `RollenGraphQLTestBase` in `src/apps/projekt/tests/test_permissions_graphql.py` mit `self.projekt`, `self._login(gruppe: str) -> None` und `self._gql(query: str, variables: dict[str, Any] | None = None) -> Any` (gibt bereits `payload["data"]` zurück) — Task 2 baut darauf auf.

- [ ] **Step 1: Die Test-Datei mit Basisklasse und den fehlschlagenden Calculation-Tests anlegen**

Create `src/apps/projekt/tests/test_permissions_graphql.py`:

```python
"""Rollenabhängige Sichtbarkeit über GraphQL (Admin/Projektleiter/Betrachter/Monteur)."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import Group, User
from django.test import TestCase
from general_manager.measurement import Measurement

from apps.projekt.models import Kostenart, KostenPosition, Projekt, ProjektStatus

_KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]

_TESTJAHR = 2024

KENNZAHLEN_QUERY = """
query {
  projektKennzahlenList {
    items {
      summeOfferteKosten { value }
    }
  }
}
"""

IST_WERT_QUERY = """
query {
  istWertList {
    items {
      kostenart { schluessel }
    }
  }
}
"""


def _lade_kostenart_daten() -> None:
    _KostenartModel.objects.bulk_create(
        [_KostenartModel(**item) for item in Kostenart._data],
        ignore_conflicts=True,
    )


def _offen() -> ProjektStatus:
    status = ProjektStatus.filter(name="Offen").first()
    assert status is not None
    return status


class RollenGraphQLTestBase(TestCase):
    """Ein Projekt mit einer Kostenposition plus Login- und GraphQL-Helfer."""

    def setUp(self) -> None:
        _lade_kostenart_daten()
        self.projekt = Projekt.create(
            ignore_permission=True,
            projekt_status=_offen(),
            name="Sichtbarkeitsprojekt",
            auftragsnummer="2024-900",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(Decimal("100000"), "CHF"),
            wv_summe=Measurement(Decimal("90000"), "CHF"),
        )
        art = Kostenart.filter(schluessel="apparate").first()
        assert isinstance(art, Kostenart)
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt.id,
            art_id=art.id,
            offerte_kosten_wert=Measurement(Decimal("20000"), "CHF"),
        )

    def _login(self, gruppe: str) -> None:
        user = User.objects.create_user(f"u_{gruppe.lower()}", password="x")
        group, _ = Group.objects.get_or_create(name=gruppe)
        user.groups.add(group)
        self.client.force_login(user)

    def _gql(self, query: str, variables: dict[str, Any] | None = None) -> Any:
        response = self.client.post(
            "/graphql/",
            data=json.dumps({"query": query, "variables": variables or {}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        return payload["data"]


class CalculationManagerSichtbarkeitTest(RollenGraphQLTestBase):
    """projektKennzahlenList/istWertList dürfen nur Berechtigte lesen."""

    def _kennzahlen(self) -> list[Any]:
        return self._gql(KENNZAHLEN_QUERY)["projektKennzahlenList"]["items"]

    def _ist_werte(self) -> list[Any]:
        return self._gql(IST_WERT_QUERY)["istWertList"]["items"]

    def test_anonym_sieht_keine_kennzahlen(self) -> None:
        self.assertEqual(self._kennzahlen(), [])

    def test_anonym_sieht_keine_ist_werte(self) -> None:
        self.assertEqual(self._ist_werte(), [])

    def test_monteur_sieht_keine_kennzahlen(self) -> None:
        self._login("Monteur")
        self.assertEqual(self._kennzahlen(), [])

    def test_monteur_sieht_keine_ist_werte(self) -> None:
        self._login("Monteur")
        self.assertEqual(self._ist_werte(), [])

    def test_betrachter_sieht_kennzahlen(self) -> None:
        self._login("Betrachter")
        self.assertNotEqual(self._kennzahlen(), [])

    def test_betrachter_sieht_keine_ist_werte(self) -> None:
        self._login("Betrachter")
        self.assertEqual(self._ist_werte(), [])

    def test_projektleiter_sieht_kennzahlen_und_ist_werte(self) -> None:
        self._login("Projektleiter")
        self.assertNotEqual(self._kennzahlen(), [])
        self.assertNotEqual(self._ist_werte(), [])
```

- [ ] **Step 2: Tests laufen lassen und das Scheitern bestätigen**

Run: `uv run --group dev pytest src/apps/projekt/tests/test_permissions_graphql.py --no-cov -q`

Expected: FAIL — die vier „sieht keine"-Tests scheitern, weil `items` befüllt statt leer ist (`AssertionError: [{...}] != []`). Die drei „sieht"-Tests sind bereits grün; das ist erwartet und beweist, dass die Query funktioniert.

- [ ] **Step 3: `CalculationPermission` wertet `__read__` statisch aus**

Ersetze in `src/apps/authentication/permission.py` die bestehende Klasse (Zeilen 49-61) durch:

```python
class CalculationPermission(AdditiveManagerPermission):
    """Permission für CalculationInterface-Manager.

    GM's Instance-Check ruft queryset.filter(id__in=...) auf, was für
    CalculationBuckets fehlschlägt (kein 'id' im identification-dict).
    Deshalb wird __read__ hier statisch ausgewertet — Gruppen-Regeln brauchen
    keine Instanz: Unberechtigte bekommen deny_all, Berechtigte alle Zeilen
    ohne Instanz-Check.

    Ein Manager ohne eigenes __read__ erbt den Settings-Default und bleibt
    damit für alle lesbar; Manager mit sensiblen Daten MÜSSEN __read__ setzen.
    """

    def get_read_permission_plan(self) -> ReadPermissionPlan:
        if not self.check_operation_permission("read"):
            return ReadPermissionPlan(
                filters=[],
                requires_instance_check=False,
                decision="deny_all",
            )
        return ReadPermissionPlan(
            filters=[{"filter": {}, "exclude": {}}],
            requires_instance_check=False,
        )
```

`ReadPermissionPlan` ist in dieser Datei bereits importiert — kein neuer Import nötig.

- [ ] **Step 4: `IstWert` bekommt ein eigenes `__read__`**

In `src/apps/projekt/calculation_manager/ist_wert.py` die Zeile `Permission = CalculationPermission` (Zeile 24) ersetzen durch:

```python
    class Permission(CalculationPermission):
        __read__ = ["isForgeAdmin", "isProjektleiter"]
```

- [ ] **Step 5: `ProjektKennzahlen` bekommt ein eigenes `__read__`**

In `src/apps/projekt/calculation_manager/projekt_kennzahlen.py` die Zeile `Permission = CalculationPermission` (Zeile 22) ersetzen durch:

```python
    class Permission(CalculationPermission):
        __read__ = ["isForgeAdmin", "isProjektleiter", "isBetrachter"]
```

- [ ] **Step 6: Tests laufen lassen und grün sehen**

Run: `uv run --group dev pytest src/apps/projekt/tests/test_permissions_graphql.py --no-cov -q`

Expected: PASS — 7 passed.

- [ ] **Step 7: Unit-Tests für den Read-Plan schreiben**

In `src/apps/authentication/tests/test_authentication.py` den Top-Level-Import erweitern:

```python
from django.contrib.auth.models import Group, User
```

und ans Ende der Datei anhängen:

```python
class CalculationPermissionReadPlanTest(TestCase):
    """CalculationPermission leitet den Read-Plan aus __read__ ab."""

    def _user(self, gruppe: str) -> User:
        user = User.objects.create_user(f"plan_{gruppe.lower()}", password="x")
        group, _ = Group.objects.get_or_create(name=gruppe)
        user.groups.add(group)
        return user

    def test_monteur_bekommt_deny_all(self) -> None:
        from apps.projekt.calculation_manager import IstWert

        plan = IstWert.Permission(
            IstWert, self._user("Monteur")
        ).get_read_permission_plan()
        self.assertEqual(plan.decision, "deny_all")
        self.assertEqual(plan.filters, [])
        self.assertFalse(plan.requires_instance_check)

    def test_projektleiter_bekommt_alle_zeilen_ohne_instanz_check(self) -> None:
        from apps.projekt.calculation_manager import IstWert

        plan = IstWert.Permission(
            IstWert, self._user("Projektleiter")
        ).get_read_permission_plan()
        self.assertNotEqual(plan.decision, "deny_all")
        self.assertEqual(plan.filters, [{"filter": {}, "exclude": {}}])
        self.assertFalse(plan.requires_instance_check)
```

Die Imports von `IstWert` stehen bewusst *in* den Methoden: `test_authentication.py` gehört zur `authentication`-App und soll beim Modul-Import nicht von `apps.projekt` abhängen.

- [ ] **Step 8: Auth-Tests laufen lassen**

Run: `uv run --group dev pytest src/apps/authentication/tests/test_authentication.py --no-cov -q`

Expected: PASS — alle Tests der Datei grün, inklusive der zwei neuen.

- [ ] **Step 9: Volles Gate und Commit**

```bash
pre-commit run --all-files
git add src/apps/authentication/permission.py \
        src/apps/projekt/calculation_manager/ist_wert.py \
        src/apps/projekt/calculation_manager/projekt_kennzahlen.py \
        src/apps/projekt/tests/test_permissions_graphql.py \
        src/apps/authentication/tests/test_authentication.py \
        docs/superpowers/plans/2026-09-12-rollen-sichtbarkeit.md
git commit -m "fix(security): Calculation-Manager nur noch für Berechtigte lesbar

projektKennzahlenList und istWertList waren über den Settings-Default
READ: [public] für jeden lesbar — auch anonym. CalculationPermission
wertet __read__ jetzt statisch aus und liefert Unberechtigten deny_all.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VBU5FCdLVkYdtv9ThCqJdQ"
```

---

### Task 2: Monteur darf Projekte lesen, aber ohne Summen und ohne Kostenpositionen

**Files:**
- Modify: `src/apps/projekt/models/projekt.py:82-89`
- Modify: `src/apps/projekt/models/kosten_position.py:56-57`
- Modify: `src/apps/projekt/tests/test_permissions_graphql.py` (Tests anhängen)

**Interfaces:**
- Consumes: `RollenGraphQLTestBase` mit `self.projekt`, `self._login(gruppe)`, `self._gql(query, variables)` aus Task 1.
- Produces: `Projekt.Permission.__read__` enthält `"isMonteur"`; `Projekt.Permission.offerte_summe` und `.wv_summe` sind `{"read": [...]}`-Dicts; `KostenPosition.Permission.__read__` ist gesetzt.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

Die beiden Query-Konstanten oben in `src/apps/projekt/tests/test_permissions_graphql.py` neben `IST_WERT_QUERY` ergänzen:

```python
PROJEKT_LISTE_QUERY = """
query {
  projektList {
    items {
      name
      offerteSumme { value }
      wvSumme { value }
    }
    pageInfo { totalCount }
  }
}
"""

PROJEKT_DETAIL_QUERY = """
query ($id: ID!) {
  projekt(id: $id) {
    name
    offerteSumme { value }
    kostenPositionenList { items { id } }
    projektKennzahlenList { items { summeOfferteKosten { value } } }
  }
}
"""
```

Und ans Ende der Datei anhängen:

```python
class ProjektSichtbarkeitTest(RollenGraphQLTestBase):
    """Projektliste und -detail je Rolle."""

    def _liste(self) -> Any:
        return self._gql(PROJEKT_LISTE_QUERY)["projektList"]

    def _detail(self) -> Any:
        return self._gql(PROJEKT_DETAIL_QUERY, {"id": str(self.projekt.id)})[
            "projekt"
        ]

    def test_monteur_sieht_projekt_ohne_summen(self) -> None:
        self._login("Monteur")
        liste = self._liste()
        self.assertEqual(liste["pageInfo"]["totalCount"], 1)
        item = liste["items"][0]
        self.assertEqual(item["name"], "Sichtbarkeitsprojekt")
        self.assertIsNone(item["offerteSumme"])
        self.assertIsNone(item["wvSumme"])

    def test_monteur_sieht_keine_kostenpositionen(self) -> None:
        self._login("Monteur")
        self.assertEqual(self._detail()["kostenPositionenList"]["items"], [])

    def test_betrachter_sieht_summen_aber_keine_kostenpositionen(self) -> None:
        self._login("Betrachter")
        detail = self._detail()
        self.assertEqual(detail["offerteSumme"]["value"], 100000.0)
        self.assertEqual(detail["kostenPositionenList"]["items"], [])
        self.assertNotEqual(detail["projektKennzahlenList"]["items"], [])

    def test_projektleiter_sieht_alles(self) -> None:
        self._login("Projektleiter")
        detail = self._detail()
        self.assertEqual(detail["offerteSumme"]["value"], 100000.0)
        self.assertNotEqual(detail["kostenPositionenList"]["items"], [])
        self.assertNotEqual(detail["projektKennzahlenList"]["items"], [])

    def test_anonym_sieht_keine_projekte(self) -> None:
        self.assertEqual(self._liste()["pageInfo"]["totalCount"], 0)
```

- [ ] **Step 2: Tests laufen lassen und das Scheitern bestätigen**

Run: `uv run --group dev pytest src/apps/projekt/tests/test_permissions_graphql.py::ProjektSichtbarkeitTest --no-cov -q`

Expected: FAIL — `test_monteur_sieht_projekt_ohne_summen` scheitert mit `0 != 1` (Monteur sieht heute gar kein Projekt), `test_betrachter_sieht_summen_aber_keine_kostenpositionen` scheitert, weil `kostenPositionenList` befüllt ist.

- [ ] **Step 3: `Projekt.Permission` erweitern**

In `src/apps/projekt/models/projekt.py` die Permission-Klasse (Zeilen 82-89) ersetzen durch:

```python
    class Permission(AdditiveManagerPermission):
        __read__ = [
            "isForgeAdmin",
            "isProjektleiter",
            "isBetrachter",
            "isMonteur",
        ]
        __create__ = ["isForgeAdmin", "isProjektleiter"]
        __update__ = ["isForgeAdmin", "isProjektleiter"]
        __delete__ = ["isForgeAdmin", "isProjektleiter"]
        graphql_capabilities: ClassVar[tuple[GraphQLPermissionCapability, ...]] = ()

        auftragsnummer = {"update": ["isAdmin"]}
        # Monteure sehen Projekte, aber keine Finanzsummen.
        offerte_summe = {"read": ["isForgeAdmin", "isProjektleiter", "isBetrachter"]}
        wv_summe = {"read": ["isForgeAdmin", "isProjektleiter", "isBetrachter"]}
```

- [ ] **Step 4: `KostenPosition.Permission` erweitern**

In `src/apps/projekt/models/kosten_position.py` die Permission-Klasse (Zeilen 56-57) ersetzen durch:

```python
    class Permission(AdditiveManagerPermission):
        __based_on__ = "projekt"
        # Einzelne Kostenpositionen sehen nur Admin und Projektleiter;
        # Betrachter bekommen nur die aggregierten ProjektKennzahlen.
        __read__ = ["isForgeAdmin", "isProjektleiter"]
```

- [ ] **Step 5: Tests laufen lassen und grün sehen**

Run: `uv run --group dev pytest src/apps/projekt/tests/test_permissions_graphql.py --no-cov -q`

Expected: PASS — 12 passed (7 aus Task 1 + 5 neue).

- [ ] **Step 6: Die übrigen Backend-Tests laufen lassen**

Run: `uv run --group dev pytest src/apps --no-cov -q`

Expected: PASS. Falls ein bestehender Test scheitert, weil er als Monteur/Betrachter auf Kostenpositionen zugreift, ist das ein echter Verhaltenswechsel — den Test an das neue Sollverhalten anpassen, nicht die Permission aufweichen.

- [ ] **Step 7: Volles Gate und Commit**

```bash
pre-commit run --all-files
git add src/apps/projekt/models/projekt.py \
        src/apps/projekt/models/kosten_position.py \
        src/apps/projekt/tests/test_permissions_graphql.py \
        docs/superpowers/plans/2026-09-12-rollen-sichtbarkeit.md
git commit -m "feat(projekt): Monteur liest Projekte ohne Summen, Betrachter ohne Kostenpositionen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VBU5FCdLVkYdtv9ThCqJdQ"
```

---

### Task 3: Capabilities aus den Permission-Klassen ableiten

**Files:**
- Modify: `src/apps/authentication/graphql_capabilities.py`
- Modify: `src/apps/authentication/tests/test_authentication.py` (Klasse `CurrentUserCapabilitiesTest`)

**Interfaces:**
- Consumes: `Projekt.Permission` mit Attribut-Regel `offerte_summe` und `KostenPosition.Permission.__read__` aus Task 2.
- Produces: `me { capabilities { canCreateProjekt canManageStundensaetze canViewFinanzen canViewKostenPositionen } }`. `canViewKostenPositionen` ist True für Admin und Projektleiter, False für Betrachter, Monteur und anonym.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

In `src/apps/authentication/tests/test_authentication.py` in der Klasse `CurrentUserCapabilitiesTest` den Query-String in `_gql` um das neue Feld ergänzen:

```python
                    "query": """
                    query {
                      me {
                        username
                        capabilities {
                          canCreateProjekt
                          canManageStundensaetze
                          canViewFinanzen
                          canViewKostenPositionen
                        }
                      }
                    }
                    """
```

Dann die drei bestehenden Erwartungs-Dicts in dieser Klasse um den neuen Schlüssel erweitern:

```python
    def test_anonymous_alle_capabilities_false(self) -> None:
        result = self._gql()
        self.assertEqual(result["data"]["me"]["username"], "")  # type: ignore[index]
        caps = result["data"]["me"]["capabilities"]  # type: ignore[index]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": False,
                "canManageStundensaetze": False,
                "canViewFinanzen": False,
                "canViewKostenPositionen": False,
            },
        )
```

```python
    def test_admin_alle_capabilities_true(self) -> None:
        user = User.objects.create_user("admincaps", password="x")
        group, _ = Group.objects.get_or_create(name="Admin")
        user.groups.add(group)
        self.client.force_login(user)
        result = self._gql()
        self.assertEqual(result["data"]["me"]["username"], "admincaps")  # type: ignore[index]
        caps = result["data"]["me"]["capabilities"]  # type: ignore[index]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": True,
                "canManageStundensaetze": True,
                "canViewFinanzen": True,
                "canViewKostenPositionen": True,
            },
        )
```

```python
    def test_monteur_darf_nur_nichts(self) -> None:
        user = User.objects.create_user("monteurcaps", password="x")
        group, _ = Group.objects.get_or_create(name="Monteur")
        user.groups.add(group)
        self.client.force_login(user)
        caps = self._gql()["data"]["me"]["capabilities"]  # type: ignore[index]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": False,
                "canManageStundensaetze": False,
                "canViewFinanzen": False,
                "canViewKostenPositionen": False,
            },
        )
```

In `test_admin_alle_capabilities_true` und `test_monteur_darf_nur_nichts` entfällt die lokale Zeile `from django.contrib.auth.models import Group` — `Group` wurde in Task 1 Schritt 7 bereits top-level importiert.

Danach zwei neue Tests an die Klasse anhängen:

```python
    def test_betrachter_sieht_finanzen_aber_keine_kostenpositionen(self) -> None:
        user = User.objects.create_user("betrachtercaps", password="x")
        group, _ = Group.objects.get_or_create(name="Betrachter")
        user.groups.add(group)
        self.client.force_login(user)
        caps = self._gql()["data"]["me"]["capabilities"]  # type: ignore[index]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": False,
                "canManageStundensaetze": False,
                "canViewFinanzen": True,
                "canViewKostenPositionen": False,
            },
        )

    def test_projektleiter_sieht_alles_ausser_benutzerverwaltung(self) -> None:
        user = User.objects.create_user("plcaps", password="x")
        group, _ = Group.objects.get_or_create(name="Projektleiter")
        user.groups.add(group)
        self.client.force_login(user)
        caps = self._gql()["data"]["me"]["capabilities"]  # type: ignore[index]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": True,
                "canManageStundensaetze": True,
                "canViewFinanzen": True,
                "canViewKostenPositionen": True,
            },
        )
```

- [ ] **Step 2: Tests laufen lassen und das Scheitern bestätigen**

Run: `uv run --group dev pytest src/apps/authentication/tests/test_authentication.py::CurrentUserCapabilitiesTest --no-cov -q`

Expected: FAIL — GraphQL kennt das Feld `canViewKostenPositionen` nicht; die Antwort enthält `errors` mit `Cannot query field 'canViewKostenPositionen'`.

- [ ] **Step 3: Capabilities aus den Permissions ableiten**

`src/apps/authentication/graphql_capabilities.py` vollständig ersetzen durch:

```python
from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from general_manager.manager.general_manager import GeneralManager
from general_manager.permission import object_capability

from apps.authentication.permission import _is_in_group


def _user_or_none(user: object) -> AbstractBaseUser | None:
    """Nur eingeloggte User weiterreichen — AnonymousUser zählt als "kein User"."""
    if isinstance(user, AbstractBaseUser):
        return user
    return None


def _can_read(
    manager: type[GeneralManager],
    user: object,
    attribute: str | None = None,
) -> bool:
    """Fragt die Permission-Klasse des Managers im Klassen-Kontext.

    Damit ist die Capability per Konstruktion deckungsgleich mit dem, was die
    GraphQL-Queries tatsächlich liefern — statt die Regel mit Gruppennamen zu
    duplizieren.
    """
    permission = manager.Permission(manager, user)
    if attribute is None:
        return permission.check_operation_permission("read")
    return permission.check_permission("read", attribute)


def _can_create_projekt(_instance: object, user: object) -> bool:
    resolved = _user_or_none(user)
    if resolved is None:
        return False
    return _is_in_group(resolved, "Admin") or _is_in_group(resolved, "Projektleiter")


def _can_manage_stundensaetze(_instance: object, user: object) -> bool:
    resolved = _user_or_none(user)
    if resolved is None:
        return False
    return _is_in_group(resolved, "Admin") or _is_in_group(resolved, "Projektleiter")


def _can_view_finanzen(_instance: object, user: object) -> bool:
    from apps.projekt.models import Projekt

    return _can_read(Projekt, user, "offerte_summe")


def _can_view_kosten_positionen(_instance: object, user: object) -> bool:
    from apps.projekt.models import KostenPosition

    return _can_read(KostenPosition, user)


class CurrentUserCapabilities:
    graphql_fields: ClassVar[dict[str, type]] = {"username": str}
    graphql_capabilities = (
        object_capability("canCreateProjekt", _can_create_projekt),
        object_capability("canManageStundensaetze", _can_manage_stundensaetze),
        object_capability("canViewFinanzen", _can_view_finanzen),
        object_capability("canViewKostenPositionen", _can_view_kosten_positionen),
    )
```

Die Manager-Imports stehen bewusst **in** den Funktionen: dieses Modul wird über den Dotted-Path in `GRAPHQL_GLOBAL_CAPABILITIES_PROVIDER` geladen, und ein Modulebenen-Import von `apps.projekt.models` würde die App-Registry zu früh anfassen.

- [ ] **Step 4: Tests laufen lassen und grün sehen**

Run: `uv run --group dev pytest src/apps/authentication/tests/test_authentication.py --no-cov -q`

Expected: PASS — alle Tests der Datei grün, inklusive der zwei neuen Rollen-Tests.

- [ ] **Step 5: Volles Gate und Commit**

```bash
pre-commit run --all-files
git add src/apps/authentication/graphql_capabilities.py \
        src/apps/authentication/tests/test_authentication.py \
        docs/superpowers/plans/2026-09-12-rollen-sichtbarkeit.md
git commit -m "feat(auth): canViewKostenPositionen + Capabilities aus Permissions abgeleitet

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VBU5FCdLVkYdtv9ThCqJdQ"
```

---

### Task 4: Frontend — Capability durchreichen, Detail-Route sperren, Listen-Navigation

**Files:**
- Modify: `frontend/src/contexts/AuthContext.tsx:11-15`
- Modify: `frontend/src/graphql/queries.ts` (Konstante `ME` am Dateiende)
- Modify: `frontend/src/App.tsx` (Route `/projekte/:id`)
- Modify: `frontend/src/pages/ProjektListePage.tsx:386-391`
- Modify: `frontend/src/pages/ProjektListePage.test.tsx`

**Interfaces:**
- Consumes: `me { capabilities { canViewKostenPositionen } }` aus Task 3.
- Produces: `AuthCapabilities` enthält `canViewKostenPositionen: boolean`; Task 5 liest sie über `useAuth()`.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

In `frontend/src/pages/ProjektListePage.test.tsx` den Mock-Block (Zeilen 13-28) ersetzen durch eine über `vi.hoisted` bereitgestellte, pro Test veränderbare Capability-Struktur:

```tsx
const { mockCapabilities } = vi.hoisted(() => ({
  mockCapabilities: {
    canCreateProjekt: true,
    canManageStundensaetze: true,
    canViewFinanzen: true,
    canViewKostenPositionen: true,
  },
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "admin",
      capabilities: mockCapabilities,
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

afterEach(() => {
  mockCapabilities.canCreateProjekt = true;
  mockCapabilities.canManageStundensaetze = true;
  mockCapabilities.canViewFinanzen = true;
  mockCapabilities.canViewKostenPositionen = true;
});
```

Den Vitest-Import in Zeile 7 um `afterEach` erweitern:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
```

Und ans Ende der Datei einen neuen Block anhängen:

```tsx
describe("ProjektListePage – Monteur ohne canViewFinanzen", () => {
  it("zeigt die Finanzspalten nicht", async () => {
    mockCapabilities.canViewFinanzen = false;
    renderPage();
    await screen.findByText("Bauprojekt B");

    expect(screen.queryByText("Offerte")).not.toBeInTheDocument();
    expect(screen.queryByText("WV + Zusätze")).not.toBeInTheDocument();
    expect(screen.queryByText("Abweichung zu Ist")).not.toBeInTheDocument();
  });

  it("navigiert bei Klick auf eine Zeile nicht in die Detailseite", async () => {
    mockCapabilities.canViewFinanzen = false;
    renderPage();
    const zelle = await screen.findByText("Bauprojekt B");

    const zeile = zelle.closest("tr");
    expect(zeile).not.toBeNull();
    fireEvent.click(zeile as HTMLElement);

    // MemoryRouter hält die History im Speicher — window.location ändert sich
    // NIE und taugt nicht als Assertion. Stattdessen prüfen, ob die Zielroute
    // gerendert wurde. Der nächste Test beweist, dass der Stub bei erlaubter
    // Navigation wirklich erscheint, diese Assertion also nicht vakuum-grün ist.
    expect(screen.queryByText("Detail-Stub 1")).not.toBeInTheDocument();
  });

  it("navigiert mit canViewFinanzen weiterhin in die Detailseite", async () => {
    renderPage();
    const zelle = await screen.findByText("Bauprojekt B");

    const zeile = zelle.closest("tr");
    expect(zeile).not.toBeNull();
    fireEvent.click(zeile as HTMLElement);

    expect(await screen.findByText("Detail-Stub 1")).toBeInTheDocument();
  });
});
```

Damit der dritte Test ein Navigationsziel hat, `renderPage` (Zeilen 85-93) um eine Stub-Route erweitern:

```tsx
function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <MockedProvider mocks={[listePage1Mock, subscriptionMock]}>
        <Routes>
          <Route path="/" element={<ProjektListePage />} />
          <Route path="/projekte/:id" element={<DetailStub />} />
        </Routes>
      </MockedProvider>
    </MemoryRouter>,
  );
}
```

Dazu oben in der Datei den Router-Import (Zeile 1) erweitern und den Stub definieren:

```tsx
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
```

```tsx
function DetailStub() {
  const { id } = useParams<{ id: string }>();
  return <p>Detail-Stub {id}</p>;
}
```

- [ ] **Step 2: Tests laufen lassen und das Scheitern bestätigen**

Run: `npm --prefix frontend test`

Expected: FAIL — „navigiert bei Klick auf eine Zeile nicht in die Detailseite" scheitert, weil die Zeile weiterhin navigiert (`expected '/projekte/1' to be '/'`). Die beiden anderen neuen Tests sind grün.

- [ ] **Step 3: `AuthCapabilities` erweitern**

In `frontend/src/contexts/AuthContext.tsx` den Typ (Zeilen 11-15) ersetzen durch:

```tsx
export type AuthCapabilities = {
  canCreateProjekt: boolean;
  canManageStundensaetze: boolean;
  canViewFinanzen: boolean;
  canViewKostenPositionen: boolean;
};
```

- [ ] **Step 4: Die `ME`-Query erweitern**

In `frontend/src/graphql/queries.ts` die Konstante `ME` ersetzen durch:

```ts
export const ME = gql`
  query Me {
    me {
      username
      capabilities {
        canCreateProjekt
        canManageStundensaetze
        canViewFinanzen
        canViewKostenPositionen
      }
    }
  }
`;
```

- [ ] **Step 5: Die Detail-Route hinter `canViewFinanzen` legen**

In `frontend/src/App.tsx` die Route `/projekte/:id` ersetzen durch:

```tsx
          <Route
            path="/projekte/:id"
            element={
              <ProtectedRoute requiredCapability="canViewFinanzen">
                <ProjektDetailPage />
              </ProtectedRoute>
            }
          />
```

`ProtectedRoute` leitet ohne die Capability nach `/projekte` um — dieses Verhalten existiert bereits und ist getestet.

- [ ] **Step 6: Die Zeilen-Navigation an `canViewFinanzen` binden**

In `frontend/src/pages/ProjektListePage.tsx` das `<tr>` der Datenzeilen (Zeilen 386-391) ersetzen durch:

```tsx
                {items.map((p) => (
                  <tr
                    key={p.id}
                    onClick={showFinancials ? () => navigate(`/projekte/${p.id}`) : undefined}
                    className={`border-b border-gray-100 last:border-0 transition-colors group${
                      showFinancials ? " hover:bg-blue-50/50 cursor-pointer" : ""
                    }`}
                  >
```

und den Chevron in der Namensspalte (Zeilen 395-403) ersetzen durch:

```tsx
                    <td className="px-4 py-3 font-medium text-gray-900">
                      <span className="inline-flex items-center gap-1">
                        {p.name}
                        {showFinancials && (
                          <ChevronRight
                            size={14}
                            className="text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity -translate-x-1 group-hover:translate-x-0 duration-150"
                          />
                        )}
                      </span>
                    </td>
```

- [ ] **Step 7: Tests laufen lassen und grün sehen**

Run: `npm --prefix frontend test`

Expected: PASS — alle Frontend-Tests grün, inklusive der drei neuen.

- [ ] **Step 8: Volles Gate und Commit**

```bash
pre-commit run --all-files
git add frontend/src/contexts/AuthContext.tsx \
        frontend/src/graphql/queries.ts \
        frontend/src/App.tsx \
        frontend/src/pages/ProjektListePage.tsx \
        frontend/src/pages/ProjektListePage.test.tsx \
        docs/superpowers/plans/2026-09-12-rollen-sichtbarkeit.md
git commit -m "feat(frontend): Detailseite hinter canViewFinanzen, Liste ohne Klick für Monteure

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VBU5FCdLVkYdtv9ThCqJdQ"
```

---

### Task 5: Frontend — Detailseite ohne Positionszeilen für Betrachter

Die Seite ist nach Task 4 nur noch für Rollen mit `canViewFinanzen` erreichbar. Die bisherigen `!showFinancials`-Zweige (Stunden-only-Ansicht für Monteure) sind damit toter Code und fliegen raus; an ihre Stelle tritt `showPositionen`.

**Files:**
- Modify: `frontend/src/pages/ProjektDetailPage.tsx:309-310, 388, 581-609, 617, 619-631, 639-676, 723-796, 802, 889`
- Modify: `frontend/src/pages/ProjektDetailPage.test.tsx`

**Interfaces:**
- Consumes: `AuthCapabilities.canViewKostenPositionen` aus Task 4.
- Produces: keine neuen Schnittstellen.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

In `frontend/src/pages/ProjektDetailPage.test.tsx` den Mock-Block (Zeilen 10-21) ersetzen durch:

```tsx
const { mockCapabilities } = vi.hoisted(() => ({
  mockCapabilities: {
    canCreateProjekt: false,
    canManageStundensaetze: false,
    canViewFinanzen: true,
    canViewKostenPositionen: true,
  },
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "betrachter",
      capabilities: mockCapabilities,
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

afterEach(() => {
  cleanup();
  mockCapabilities.canViewFinanzen = true;
  mockCapabilities.canViewKostenPositionen = true;
});
```

Die separate Zeile `afterEach(cleanup);` (Zeile 23) entfällt dadurch — `cleanup()` passiert jetzt im kombinierten Hook.

Damit das Diagramm überhaupt Daten hat, in `projektMock` (Zeilen 40-42) die drei leeren Listen ersetzen durch:

```tsx
          projektKennzahlenList: {
            items: [
              {
                summeOfferteKosten: { value: 500, unit: "CHF" },
                summeWvKosten: { value: 450, unit: "CHF" },
                summeIstKosten: { value: 400, unit: "CHF" },
                verbrauchsrate: 80,
                deltaWvOff: { value: -50, unit: "CHF" },
                deltaWvOffPct: -10,
                deltaIstPlan: { value: -50, unit: "CHF" },
                deltaIstPlanPct: -11.1,
                summeWvPlus: { value: 450, unit: "CHF" },
                bisherVerrechnet: { value: -400, unit: "CHF" },
              },
            ],
          },
          kostenPositionenList: {
            items: [
              {
                id: "10",
                art: { schluessel: "apparate" },
                offerteKostenWert: { value: 500, unit: "CHF" },
                offerteStunden: null,
                wvKostenWert: { value: 450, unit: "CHF" },
                wvKostenWertProzent: 100,
                offerteKostenWertProzent: 100,
              },
            ],
          },
          istWertList: {
            items: [
              {
                kostenart: { schluessel: "apparate" },
                istKostenWert: { value: 400, unit: "CHF" },
                istKostenWertProzent: 100,
              },
            ],
          },
```

Und ans Ende der Datei anhängen:

```tsx
describe("ProjektDetailPage – Positionszeilen folgen canViewKostenPositionen", () => {
  it("zeigt Positionszeilen, Legende und Diagramm, wenn die Capability gesetzt ist", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    await screen.findByText("Testprojekt");

    expect(screen.getByText("Apparate")).toBeInTheDocument();
    expect(screen.getByText("berechnet")).toBeInTheDocument();
    expect(screen.getByText("Projektstatus auf einen Blick")).toBeInTheDocument();
  });

  it("versteckt Positionszeilen, Legende und Diagramm ohne die Capability", async () => {
    mockCapabilities.canViewKostenPositionen = false;
    renderPage({ canUpdate: false, canDelete: false });
    await screen.findByText("Testprojekt");

    expect(screen.queryByText("Apparate")).not.toBeInTheDocument();
    expect(screen.queryByText("berechnet")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Projektstatus auf einen Blick"),
    ).not.toBeInTheDocument();
  });

  it("zeigt Header-Summen und den Footer auch ohne Positionszeilen", async () => {
    mockCapabilities.canViewKostenPositionen = false;
    renderPage({ canUpdate: false, canDelete: false });
    await screen.findByText("Testprojekt");

    expect(screen.getByText("Offerte exkl. MwSt.")).toBeInTheDocument();
    expect(screen.getByText("WV-Summe exkl. MwSt.")).toBeInTheDocument();
    expect(screen.getByText("Summe der Kosten")).toBeInTheDocument();
    expect(screen.getByText("Gewinn / Verlust")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Tests laufen lassen und das Scheitern bestätigen**

Run: `npm --prefix frontend test`

Expected: FAIL — „versteckt Positionszeilen, Legende und Diagramm ohne die Capability" scheitert, weil `Apparate` weiterhin gerendert wird (die Seite kennt `canViewKostenPositionen` noch nicht).

- [ ] **Step 3: `showFinancials` durch `showPositionen` ersetzen**

In `frontend/src/pages/ProjektDetailPage.tsx` Zeile 310 ersetzen:

```tsx
  const showPositionen = user?.capabilities.canViewKostenPositionen ?? false;
```

und Zeile 388 ersetzen:

```tsx
  const visibleReihen = showPositionen ? allReihen : [];
```

> **Hinweis:** Zwischen Step 3 und Step 8 referenziert die Datei ein nicht
> mehr existierendes `showFinancials` und kompiliert nicht. Das ist erwartet —
> die Tests laufen erst wieder in Step 9.

- [ ] **Step 4: Header-Summen immer rendern**

Im Grid der Header-Card (Zeilen 581-609) exakt diese zwei Zeilen **löschen**:

```tsx
              {showFinancials && (
                <>
```

und exakt diese zwei Zeilen **löschen**:

```tsx
                </>
              )}
```

Die drei dazwischenliegenden `<div>`-Blöcke (Offerte exkl. MwSt., WV-Summe exkl. MwSt., Plan-WV-Summe exkl. MwSt.) bleiben unverändert stehen und werden dadurch unbedingt gerendert. Die Einrückung der drei Blöcke um eine Ebene nach links ziehen.

- [ ] **Step 5: Überschrift und Legende der Kostenpositionen-Card**

Zeile 617 ersetzen durch:

```tsx
                Kostenpositionen
```

und die Bedingung der Legende in Zeile 619 ersetzen durch:

```tsx
              {showPositionen && (
```

- [ ] **Step 6: Tabellenkopf entrümpeln**

Im `<thead>` direkt nach dem `<th>…Art</th>` exakt diese zwei Zeilen **löschen**:

```tsx
                    {showFinancials && (
                      <>
```

Danach exakt diese zwei Zeilen **löschen** (sie stehen unmittelbar nach dem letzten `<th>` mit „%" und dem `Database`-Icon):

```tsx
                      </>
                    )}
```

Die neun dazwischenliegenden `<th>` (Soll-Offerte, %, Soll-WV, %, Plan-WV, %, Ist, %) bleiben stehen und werden dadurch unbedingt gerendert; ihre Einrückung um eine Ebene nach links ziehen.

Anschließend den kompletten folgenden Block mit den beiden Stunden-Spalten **löschen**:

```tsx
                    {!showFinancials && (
                      <>
                        <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-right">Ist</th>
                        <th className="px-4 py-3 text-[11px] uppercase tracking-wider font-semibold text-gray-500 text-right">Ist %</th>
                      </>
                    )}
```

- [ ] **Step 7: Tabellenzeilen entrümpeln**

In der Datenzeile im `<tbody>` direkt nach dem schließenden `</td>` der Art-Spalte exakt diese zwei Zeilen **löschen**:

```tsx
                        {showFinancials && (
                          <>
```

Danach exakt diese zwei Zeilen **löschen** (sie stehen unmittelbar nach dem `<td className={istCls}>` mit `pct(istWert?.istKostenWertProzent ?? null)`):

```tsx
                          </>
                        )}
```

Die acht dazwischenliegenden `<td>` bleiben stehen und werden dadurch unbedingt gerendert; ihre Einrückung um eine Ebene nach links ziehen.

Anschließend den kompletten folgenden Block **löschen**:

```tsx
                        {!showFinancials && (
                          <>
                            <td className="px-4 py-2 text-right text-gray-700 tabular-nums">{istDisplay}</td>
                            <td className="px-4 py-2 text-right tabular-nums font-medium"
                              style={istWert?.istKostenWertProzent != null && istWert.istKostenWertProzent > 100 ? { color: "var(--forge-red)" } : {}}>
                              {pct(istWert?.istKostenWertProzent ?? null)}
                            </td>
                          </>
                        )}
```

- [ ] **Step 8: Footer und Diagramm**

Zeile 802 ersetzen durch:

```tsx
                  {p && (
```

und Zeile 889 ersetzen durch:

```tsx
          {showPositionen && <ProjectVisualization rows={vizRows} />}
```

- [ ] **Step 9: Tests laufen lassen und grün sehen**

Run: `npm --prefix frontend test`

Expected: PASS — alle Frontend-Tests grün, inklusive der drei neuen.

- [ ] **Step 10: Typen und Lint prüfen**

Run: `npm --prefix frontend run build`

Expected: Erfolgreich — kein `TS6133` über ein ungenutztes `showFinancials` und kein ungenutzter Import. Falls doch, die betreffende Variable bzw. den Import entfernen.

- [ ] **Step 11: Volles Gate und Commit**

```bash
pre-commit run --all-files
git add frontend/src/pages/ProjektDetailPage.tsx \
        frontend/src/pages/ProjektDetailPage.test.tsx \
        docs/superpowers/plans/2026-09-12-rollen-sichtbarkeit.md
git commit -m "feat(frontend): Positionszeilen und Diagramm nur mit canViewKostenPositionen

Die Stunden-only-Ansicht für Monteure entfällt — die Detailseite ist
nach dem Route-Guard nur noch für Rollen mit canViewFinanzen erreichbar.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VBU5FCdLVkYdtv9ThCqJdQ"
```

---

### Task 6: Dokumentation nachziehen

**Files:**
- Modify: `CONTEXT.md:34-35`
- Modify: `.claude/skills/general-manager/references/reference.md:564-585`

**Interfaces:**
- Consumes: das fertige Verhalten aus Task 1-5.
- Produces: keine Code-Schnittstellen.

- [ ] **Step 1: Rollenbeschreibung in `CONTEXT.md` präzisieren**

Die Zeilen 34-35 ersetzen durch:

```markdown
  - **Betrachter** (1×, Inhaber/GF) — Lesezugriff auf Projekte und aggregierte Kennzahlen; keine einzelnen Kostenpositionen, kein Diagramm; keine Bearbeitung
  - **Monteur** (2×) — Projektliste ohne Finanzspalten, kein Zugriff auf die Projektdetails; Stundenerfassung in Phase 2
```

- [ ] **Step 2: `CalculationPermission` in der GM-Referenz aktualisieren**

In `.claude/skills/general-manager/references/reference.md` das Code-Beispiel im Abschnitt „### `CalculationPermission` (Forge-Pattern)" (Zeilen 566-573) ersetzen durch:

````markdown
```python
class CalculationPermission(AdditiveManagerPermission):
    def get_read_permission_plan(self) -> ReadPermissionPlan:
        if not self.check_operation_permission("read"):
            return ReadPermissionPlan(
                filters=[], requires_instance_check=False, decision="deny_all"
            )
        return ReadPermissionPlan(
            filters=[{"filter": {}, "exclude": {}}],
            requires_instance_check=False,
        )
```
````

und direkt nach dem Absatz, der mit „Pflicht für jeden `CalculationInterface`-Manager" beginnt (Zeilen 575-578), einen neuen Absatz einfügen:

```markdown
> **Jeder Calculation-Manager mit sensiblen Daten braucht ein eigenes `__read__`.**
> Ohne `__read__` greift der Settings-Default (`READ: ["public"]`) und der
> Manager ist für jeden lesbar — auch anonym, auch wenn der Basis-Manager
> (z. B. `Projekt`) längst eingeschränkt ist. `CalculationPermission` wertet
> `__read__` statisch aus (Gruppen-Regeln brauchen keine Instanz) und liefert
> Unberechtigten `deny_all`, also leere Listen.
```

- [ ] **Step 3: Volles Gate und Commit**

```bash
pre-commit run --all-files
git add CONTEXT.md \
        .claude/skills/general-manager/references/reference.md \
        docs/superpowers/plans/2026-09-12-rollen-sichtbarkeit.md
git commit -m "docs: Rollenbeschreibung und CalculationPermission-Referenz nachgezogen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VBU5FCdLVkYdtv9ThCqJdQ"
```

---

## Abschluss

Nach Task 6 einmal das Sollverhalten am laufenden Stack gegenprüfen (Compose-Smoke-Test auf dem Host, siehe `CLAUDE.md`): mit dem Dev-Seed-User `tina` (Gruppe Betrachter) einloggen, Projektdetailseite öffnen — Header-Summen und Footer sichtbar, keine Positionszeilen, kein Diagramm.

Dann `superpowers:finishing-a-development-branch` für die Integration.
