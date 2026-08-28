# ProjektStatus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `Projekt.auftrag_fertig` (Boolean) with `Projekt.projekt_status` (FK to a new `ProjektStatus` read-only lookup manager with three values: Offen, In Arbeit, Fertig), end-to-end (backend model, migration, GraphQL, frontend).

**Architecture:** `ProjektStatus` is a `GeneralManager` with a `ReadOnlyInterface` (static `_data`), exactly mirroring the existing `Kostenart` model in this codebase. `Projekt.projekt_status` is a `ForeignKey` to `ProjektStatus`, exactly mirroring the existing `KostenPosition.art` FK. No new architectural pattern is introduced — both precedents already exist and are followed file-for-file.

**Tech Stack:** Django + GeneralManager (GM) v0.76.0, pytest/pytest-django, React + TypeScript + Apollo Client, Vitest.

## Global Constraints

- Run all backend/frontend commands inside the project's DevContainer (`test -f /.dockerenv` must succeed) — see `CLAUDE.md`.
- No `--no-verify` on any commit — the pre-commit gate (ruff, pytest, mypy, vitest) must pass.
- No "Stammdaten" page/route in the frontend — `ProjektStatus` is not user-editable via the UI (see spec, Nicht-Ziele).
- Field access on GM instances always via `self.feldname`, never `self._interface._instance`.
- Every commit message ends with: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
- Reference spec: `docs/superpowers/specs/2026-08-28-projekt-status-design.md`

---

### Task 1: `ProjektStatus` GeneralManager (read-only lookup)

**Files:**
- Create: `src/apps/projekt/models/projekt_status.py`
- Create: `src/apps/projekt/tests/test_projekt_status.py`
- Modify: `src/apps/projekt/models/__init__.py`
- Create: migration in `src/apps/projekt/migrations/` (auto-generated, expected name `0006_projektstatus.py` — verify actual name after running `makemigrations`)

**Interfaces:**
- Produces: `ProjektStatus` (GM class) with field `name: str`, class attribute `_data` (list of `{"name": ...}` dicts, 3 entries: "Offen", "In Arbeit", "Fertig"), `ProjektStatus.Interface._model` (raw Django model, for direct ORM seeding in tests/migrations, exactly like `Kostenart.Interface._model`).

- [ ] **Step 1: Write the failing test**

Create `src/apps/projekt/tests/test_projekt_status.py`:

```python
"""Tests für apps/projekt/models/projekt_status.py."""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError
from django.test import TestCase

from apps.projekt.models import ProjektStatus

_ProjektStatusModel: Any = ProjektStatus.Interface._model  # type: ignore[misc]


class ProjektStatusDatenTest(TestCase):
    """Prüft den statischen _data-Katalog von ProjektStatus."""

    def setUp(self) -> None:
        _ProjektStatusModel.objects.bulk_create(
            [_ProjektStatusModel(**item) for item in ProjektStatus._data],
            ignore_conflicts=True,
        )

    def test_alle_3_eintraege_vorhanden(self) -> None:
        self.assertEqual(ProjektStatus.filter().count(), 3)

    def test_namen_sind_offen_in_arbeit_fertig(self) -> None:
        namen = {s.name for s in ProjektStatus.filter()}
        self.assertEqual(namen, {"Offen", "In Arbeit", "Fertig"})

    def test_name_unique_constraint(self) -> None:
        with self.assertRaises(IntegrityError):
            _ProjektStatusModel.objects.create(name="Offen")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group dev pytest src/apps/projekt/tests/test_projekt_status.py -v`
Expected: FAIL/ERROR — `ImportError: cannot import name 'ProjektStatus' from 'apps.projekt.models'`

- [ ] **Step 3: Create the model**

Create `src/apps/projekt/models/projekt_status.py`:

```python
from __future__ import annotations

from django.db import models
from general_manager import (
    AdditiveManagerPermission,
    GeneralManager,
    ReadOnlyInterface,
)


class ProjektStatus(GeneralManager):
    """Statische Liste der Projekt-Status (Offen, In Arbeit, Fertig)."""

    id: int
    name: str

    _data = [
        {"name": "Offen"},
        {"name": "In Arbeit"},
        {"name": "Fertig"},
    ]

    class Interface(ReadOnlyInterface):
        name = models.CharField(max_length=50, unique=True)

        class Meta:
            verbose_name = "Projekt-Status"
            verbose_name_plural = "Projekt-Status"
            db_table = "projekt_projektstatus"

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["isAdmin"]
        __update__ = ["isAdmin"]
        __delete__ = ["isAdmin"]
```

- [ ] **Step 4: Register in the app's model package**

Modify `src/apps/projekt/models/__init__.py` (full file):

```python
from __future__ import annotations

from .kosten_position import KostenPosition
from .kostenart import Kostenart
from .projekt_status import ProjektStatus
from .projekt import Projekt

__all__ = ["Projekt", "KostenPosition", "Kostenart", "ProjektStatus"]
```

- [ ] **Step 5: Generate the migration**

Run: `uv run python manage.py makemigrations projekt`
Expected output: a new migration listing `Create model ProjektStatus`. Note the exact filename it created (e.g. `0006_projektstatus.py`) — you'll reference the previous migration's dependency name in Task 2.

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run --group dev pytest src/apps/projekt/tests/test_projekt_status.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add src/apps/projekt/models/projekt_status.py src/apps/projekt/models/__init__.py src/apps/projekt/tests/test_projekt_status.py src/apps/projekt/migrations/
git commit -m "feat: ProjektStatus als ReadOnly-Lookup (Offen/In Arbeit/Fertig)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `Projekt.projekt_status` — add, backfill, remove `auftrag_fertig`

**Files:**
- Modify: `conftest.py` (repo root)
- Modify: `src/apps/projekt/models/projekt.py`
- Modify: `src/apps/projekt/tests/test_projekt.py`
- Modify: `src/apps/projekt/admin.py`
- Modify: `tests/test_graphql_queries.py`
- Create: 3 migrations in `src/apps/projekt/migrations/` (expected `0007_projekt_projekt_status.py`, `0008_backfill_projekt_status.py`, `0009_...` — verify actual names)

**Interfaces:**
- Consumes: `ProjektStatus` (Task 1) — `ProjektStatus.filter(name="Offen").first()`, `ProjektStatus.Interface._model`, `ProjektStatus._data`.
- Produces: `Projekt.projekt_status: ProjektStatus` (non-null FK), `Projekt.create()` defaults `projekt_status` to "Offen" when not supplied.

#### Part A: global test fixture (needed before `Projekt.create()` requires a status)

- [ ] **Step 1: Add the autouse seed fixture**

Read `conftest.py` first (to preserve the existing `clear_django_cache` fixture), then modify it to this full content:

```python
from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def clear_django_cache() -> None:
    """
    Leert den Django-Cache vor jedem Test.

    Nötig weil @graph_ql_property die berechneten Werte per django_cache
    speichert. Ohne Leeren würden Cache-Einträge aus früheren Tests
    falsche Werte an Folgetests zurückliefern.
    """
    from django.core.cache import cache

    cache.clear()


@pytest.fixture(autouse=True)
def _seed_projekt_status(db: None) -> None:
    """
    Sorgt dafür, dass die drei ProjektStatus-Einträge (Offen/In Arbeit/Fertig)
    vor jedem Test existieren.

    Projekt.create() braucht ProjektStatus.filter(name="Offen") für seinen
    Default. ReadOnlyInterface synct _data zwar beim App-Start, aber nicht
    zuverlässig gegen die pytest-Testdatenbank — aus demselben Grund seeden
    die Kostenart-Tests in diesem Projekt ebenfalls manuell (siehe
    test_kostenart.py, test_kosten_position.py).
    """
    from apps.projekt.models import ProjektStatus

    model: Any = ProjektStatus.Interface._model
    model.objects.bulk_create(
        [model(**item) for item in ProjektStatus._data],
        ignore_conflicts=True,
    )
```

This fixture has no test of its own — it's verified implicitly by every test in Part B/C that calls `Projekt.create()` without an explicit `projekt_status`.

#### Part B: add the field (nullable), default logic, migration

- [ ] **Step 2: Write the failing test**

Modify `src/apps/projekt/tests/test_projekt.py`: replace the `test_auftrag_fertig_default_ist_false` test (currently at line ~98) with:

```python
    def test_projekt_status_default_ist_offen(self) -> None:
        proj = Projekt.create(
            ignore_permission=True,
            name="Standard Flags 2",
            auftragsnummer="2024-006",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_KLEIN, "CHF"),
        )
        self.assertEqual(proj.projekt_status.name, "Offen")
```

Also modify `test_felder_vorhanden` (currently at line ~38) — replace `"auftrag_fertig",` with `"projekt_status",` in the tuple of expected field names.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --group dev pytest src/apps/projekt/tests/test_projekt.py -v`
Expected: FAIL — `AttributeError: 'Projekt' object has no attribute 'projekt_status'`

- [ ] **Step 4: Add the field to the model**

Modify `src/apps/projekt/models/projekt.py`. Add the import (after the existing `general_manager.rule` import):

```python
from apps.projekt.models.projekt_status import ProjektStatus
```

Change the type annotation `auftrag_fertig: bool` (line 38) to:

```python
    projekt_status: ProjektStatus
```

In `class Interface(DatabaseInterface)`, change `auftrag_fertig = models.BooleanField(default=False)` (line 59) to:

```python
        projekt_status = models.ForeignKey(
            "projekt.ProjektStatus",
            on_delete=models.PROTECT,
            related_name="projekte",
            null=True,
            blank=True,
        )
        auftrag_fertig = models.BooleanField(default=False)
```

(Both fields coexist temporarily — `auftrag_fertig` is removed in Part C after the data backfill.)

In `create()`, after the existing `projektleiter` handling, add:

```python
        if kwargs.get("projekt_status") is None:
            kwargs["projekt_status"] = ProjektStatus.filter(name="Offen").first()
```

So the full `create()` method reads:

```python
    @classmethod
    def create(
        cls,
        creator_id: int | None = None,
        history_comment: str | None = None,
        ignore_permission: bool = False,
        **kwargs: Any,
    ) -> Projekt:
        if "projektleiter" in kwargs and kwargs["projektleiter"] is not None:
            kwargs["projektleiter_id"] = int(kwargs.pop("projektleiter"))
        if kwargs.get("projekt_status") is None:
            kwargs["projekt_status"] = ProjektStatus.filter(name="Offen").first()
        return super().create(
            creator_id=creator_id,
            history_comment=history_comment,
            ignore_permission=ignore_permission,
            **kwargs,
        )
```

- [ ] **Step 5: Generate the migration**

Run: `uv run python manage.py makemigrations projekt`
Expected: one migration adding `projekt_status` (nullable FK) to `Projekt`. Note the filename.

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run --group dev pytest src/apps/projekt/tests/test_projekt.py -v`
Expected: PASS (all tests, including `test_projekt_status_default_ist_offen`)

- [ ] **Step 7: Commit**

```bash
git add conftest.py src/apps/projekt/models/projekt.py src/apps/projekt/tests/test_projekt.py src/apps/projekt/migrations/
git commit -m "feat: Projekt.projekt_status hinzufügen (nullable, Default Offen)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

#### Part C: backfill existing data, then finalize (remove `auftrag_fertig`, make FK required)

- [ ] **Step 8: Hand-write the data migration**

Run: `ls src/apps/projekt/migrations/` and note the migration filename from Step 5 (Part B) — use its name (without `.py`) as the `dependencies` entry below.

Create `src/apps/projekt/migrations/0008_backfill_projekt_status.py` (adjust the number if Step 5 generated something other than `0007`):

```python
from __future__ import annotations

from django.db import migrations


def backfill_projekt_status(apps, schema_editor):
    ProjektStatusModel = apps.get_model("projekt", "ProjektStatus")
    ProjektModel = apps.get_model("projekt", "Projekt")

    offen, _ = ProjektStatusModel.objects.get_or_create(name="Offen")
    in_arbeit, _ = ProjektStatusModel.objects.get_or_create(name="In Arbeit")
    fertig, _ = ProjektStatusModel.objects.get_or_create(name="Fertig")

    ProjektModel.objects.filter(auftrag_fertig=True).update(projekt_status=fertig)
    ProjektModel.objects.filter(auftrag_fertig=False).update(projekt_status=in_arbeit)


def noop_reverse(apps, schema_editor):
    """Kein Rückweg nötig — auftrag_fertig existiert in dieser Migration noch."""


class Migration(migrations.Migration):
    dependencies = [
        ("projekt", "0007_projekt_projekt_status"),  # <- ersetze mit dem echten Namen aus Step 5
    ]

    operations = [
        migrations.RunPython(backfill_projekt_status, noop_reverse),
    ]
```

- [ ] **Step 9: Apply migrations and manually verify the backfill**

Run: `uv run python manage.py migrate projekt`
Expected: migrations `0007` (or whatever Step 5 generated) and `0008_backfill_projekt_status` apply cleanly.

Verify with a one-off shell check:

Run:
```bash
uv run python manage.py shell -c "
from apps.projekt.models import Projekt
for p in Projekt.filter():
    print(p.auftragsnummer, p.auftrag_fertig, p.projekt_status.name if p.projekt_status else None)
"
```
Expected: every row shows `projekt_status` name `Fertig` when `auftrag_fertig` was `True`, `In Arbeit` when `False`; no row shows `None`.

- [ ] **Step 10: Remove `auftrag_fertig`, make `projekt_status` required**

Modify `src/apps/projekt/models/projekt.py`:

- Remove the line `auftrag_fertig = models.BooleanField(default=False)` from `Interface`.
- Change the `projekt_status` field to drop `null=True, blank=True`:

```python
        projekt_status = models.ForeignKey(
            "projekt.ProjektStatus",
            on_delete=models.PROTECT,
            related_name="projekte",
        )
```

- [ ] **Step 11: Generate the finalizing migration**

Run: `uv run python manage.py makemigrations projekt`
Expected: one migration with `AlterField` (projekt_status, `null=False`) and `RemoveField` (auftrag_fertig).

Run: `uv run python manage.py migrate projekt`
Expected: applies cleanly (no NOT NULL violations — Step 9 already backfilled every row).

- [ ] **Step 12: Update `admin.py`**

Modify `src/apps/projekt/admin.py`:

```python
from django.contrib import admin

from apps.projekt.models import KostenPosition, Projekt


@admin.register(Projekt.Interface._model)  # type: ignore[misc]
class ProjektAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "auftragsnummer",
        "name",
        "projektleiter",
        "wv_summe",
        "projekt_status",
    )
    list_filter = ("projekt_status",)
    search_fields = ("name", "auftragsnummer")


@admin.register(KostenPosition.Interface._model)  # type: ignore[misc]
class KostenPositionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("projekt", "art", "offerte_kosten_wert")
    list_filter = ("art",)
    raw_id_fields = ("projekt",)
```

- [ ] **Step 13: Update the GraphQL integration test**

Modify `tests/test_graphql_queries.py`:

In `_QUERY_PROJEKT_LISTE`, replace the line `auftragFertig` with `projektStatus { name }`.
In `_QUERY_PROJEKT_DETAIL`, replace the line `auftragFertig` with `projektStatus { name }`.

In `test_projekt_liste_shape`, add after `self.assertIn("projektKennzahlenList", p)`:

```python
        self.assertEqual(p["projektStatus"]["name"], "Offen")
```

In `test_projekt_detail_shape`, add after `self.assertEqual(p["auftragsnummer"], "T-2026-001")`:

```python
        self.assertEqual(p["projektStatus"]["name"], "Offen")
```

- [ ] **Step 14: Run the full backend test suite**

Run: `uv run --group dev pytest src/apps/projekt tests/ -v`
Expected: PASS, all tests green (no remaining reference to `auftrag_fertig` anywhere in `src/` or `tests/`).

Verify: `grep -rn "auftrag_fertig" src/ tests/` → no output.

- [ ] **Step 15: Commit**

```bash
git add src/apps/projekt/models/projekt.py src/apps/projekt/admin.py src/apps/projekt/migrations/ tests/test_graphql_queries.py
git commit -m "feat: auftrag_fertig entfernen, Projekt.projekt_status verpflichtend

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend GraphQL layer

**Files:**
- Modify: `frontend/src/graphql/queries.ts`
- Modify: `frontend/src/graphql/mutations.ts`
- Modify: `frontend/src/graphql/subscriptions.ts`

**Interfaces:**
- Produces: `GET_PROJEKT_STATUS_IDS` query (returns `{ projektStatusList: { items: { id: string; name: string }[] } }`), used by Task 5.

- [ ] **Step 1: Update `queries.ts`**

In `GET_PROJEKTE` (the `_QUERY_PROJEKT_LISTE`-equivalent), replace the line `auftragFertig` with:

```
        projektStatus {
          id
          name
        }
```

In `SEARCH_PROJEKTE`, replace the line `auftragFertig` (inside `... on ProjektType`) the same way.

In `GET_PROJEKT`, replace the line `auftragFertig` the same way.

Add a new query at the end of the file (after `GET_KOSTENART_IDS`, before `GET_FEHLENDE_STUNDENSATZ_JAHRE`):

```typescript
export const GET_PROJEKT_STATUS_IDS = gql`
  query ProjektStatusIds {
    projektStatusList {
      items {
        id
        name
      }
    }
  }
`;
```

- [ ] **Step 2: Update `mutations.ts`**

In `UPDATE_PROJEKT`, replace `$auftragFertig: Boolean` with `$projektStatus: ID`, and replace `auftragFertig: $auftragFertig` with `projektStatus: $projektStatus`. Full updated mutation:

```typescript
export const UPDATE_PROJEKT = gql`
  mutation UpdateProjekt(
    $id: Int!
    $name: String
    $offerteSumme: MeasurementScalar
    $wvSumme: MeasurementScalar
    $projektleiter: String
    $projektStatus: ID
  ) {
    updateProjekt(
      id: $id
      name: $name
      offerteSumme: $offerteSumme
      wvSumme: $wvSumme
      projektleiter: $projektleiter
      projektStatus: $projektStatus
    ) {
      success
    }
  }
`;
```

(`CREATE_PROJEKT` is unchanged — new projects get the "Offen" default from the backend.)

- [ ] **Step 3: Update `subscriptions.ts`**

In `PROJEKT_DETAIL_SUBSCRIPTION`, replace the line `auftragFertig` with:

```
        projektStatus {
          id
          name
        }
```

- [ ] **Step 4: Verify no stale references remain**

Run: `grep -rn "auftragFertig" frontend/src/graphql/`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/graphql/queries.ts frontend/src/graphql/mutations.ts frontend/src/graphql/subscriptions.ts
git commit -m "feat(frontend): GraphQL-Layer auf projektStatus umstellen

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `ProjektListePage` — 3-state status badge

**Files:**
- Modify: `frontend/src/pages/ProjektListePage.tsx`
- Modify: `frontend/src/pages/ProjektListePage.test.tsx`

**Interfaces:**
- Consumes: `Projekt.projektStatus: { id: string; name: string }` (Task 3's `GET_PROJEKTE`/`SEARCH_PROJEKTE`).

- [ ] **Step 1: Write the failing test**

Modify `frontend/src/pages/ProjektListePage.test.tsx`. In the `projekt()` factory function, replace the line `auftragFertig: false,` with:

```typescript
    projektStatus: { id: "2", name: "In Arbeit" },
```

Add a new test after the existing tests in the file (find the last `it(...)` block and add this one after it, inside the same `describe`):

```typescript
  it("zeigt den ProjektStatus-Namen als Badge an", async () => {
    renderPage();
    expect(await screen.findByText("Bauprojekt B")).toBeInTheDocument();
    expect(screen.getAllByText("In Arbeit").length).toBeGreaterThan(0);
  });
```

(`renderPage()` is the existing helper in this file that renders `<ProjektListePage />` wrapped in `<MockedProvider mocks={[listePage1Mock, subscriptionMock]}>` — reuse it as-is.)

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- ProjektListePage`
Expected: FAIL — badge still renders "Aktiv"/"Archiviert", not "In Arbeit"; also a TypeScript error since `Projekt.auftragFertig` no longer matches the mock shape (once Step 3 changes the type).

- [ ] **Step 3: Update the type and StatusBadge component**

Modify `frontend/src/pages/ProjektListePage.tsx`. Replace the `Projekt` type's `auftragFertig: boolean;` line with:

```typescript
  projektStatus: { id: string; name: string };
```

Replace the entire `StatusBadge` function with:

```typescript
const STATUS_STYLES: Record<string, string> = {
  Offen: "bg-blue-50 text-blue-700 ring-blue-200",
  "In Arbeit": "bg-emerald-50 text-emerald-700 ring-emerald-200",
  Fertig: "bg-gray-50 text-gray-500 ring-gray-200",
};

const STATUS_DOTS: Record<string, string> = {
  Offen: "bg-blue-500",
  "In Arbeit": "bg-emerald-500",
  Fertig: "bg-gray-400",
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.Offen;
  const dot = STATUS_DOTS[status] ?? STATUS_DOTS.Offen;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ring-1 ring-inset ${style}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      {status}
    </span>
  );
}
```

Replace the table-row usage `<StatusBadge archived={p.auftragFertig} />` with:

```tsx
                      <StatusBadge status={p.projektStatus.name} />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- ProjektListePage`
Expected: PASS, all tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ProjektListePage.tsx frontend/src/pages/ProjektListePage.test.tsx
git commit -m "feat(frontend): 3-Wege-Status-Badge in der Projektliste

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: `ProjektDetailPage` — status as a dropdown in the edit form

**Files:**
- Modify: `frontend/src/pages/ProjektDetailPage.tsx`

**Interfaces:**
- Consumes: `GET_PROJEKT_STATUS_IDS` (Task 3), `Projekt.projektStatus: { id: string; name: string }` (Task 3's `GET_PROJEKT`), `UPDATE_PROJEKT`'s `$projektStatus: ID` (Task 3).

- [ ] **Step 1: Update imports and types**

In `frontend/src/pages/ProjektDetailPage.tsx`, change the import line:

```typescript
import { GET_KOSTENART_IDS, GET_PROJEKT } from "../graphql/queries";
```

to:

```typescript
import { GET_KOSTENART_IDS, GET_PROJEKT, GET_PROJEKT_STATUS_IDS } from "../graphql/queries";
```

Replace the `Projekt` type's `auftragFertig: boolean;` line with:

```typescript
  projektStatus: { id: string; name: string };
```

Replace the `HeaderForm` type line:

```typescript
type HeaderForm = { name: string; offerteSumme: string; wvSumme: string; projektleiter: string };
```

with:

```typescript
type HeaderForm = { name: string; offerteSumme: string; wvSumme: string; projektleiter: string; projektStatus: string };
```

Add two new types right after `KostenartIdsData`:

```typescript
type ProjektStatusIdItem = { id: string; name: string };
type ProjektStatusIdsData = { projektStatusList: { items: ProjektStatusIdItem[] } };
```

- [ ] **Step 2: Load the status options**

Directly below the existing `kostenartData` query hook (`const { data: kostenartData } = useQuery<KostenartIdsData>(GET_KOSTENART_IDS);`), add:

```typescript
  const { data: projektStatusData } = useQuery<ProjektStatusIdsData>(GET_PROJEKT_STATUS_IDS);
```

- [ ] **Step 3: Include status in `startEditHeader()`**

In `startEditHeader()`, the `setHeaderForm({...})` call currently sets `name`, `offerteSumme`, `wvSumme`, `projektleiter`. Add `projektStatus: p.projektStatus.id,` as an additional key in that object (any position).

- [ ] **Step 4: Include status in `saveHeader()`**

In `saveHeader()`, the `updateProjekt({ variables: {...} })` call currently passes `id`, `name`, `offerteSumme`, `wvSumme`, `projektleiter`. Add `projektStatus: headerForm.projektStatus || undefined` as an additional key in that `variables` object.

- [ ] **Step 5: Remove the old toggle button and function**

Delete the `toggleArchivieren()` function entirely (it calls `updateProjekt({ variables: { id: p.id, auftragFertig: !p.auftragFertig } })`).

In the header JSX, delete this block:

```tsx
                {!editingHeader && p.auftragFertig && (
                  <span className="rounded px-2.5 py-1 text-xs font-medium bg-gray-100 text-gray-600">Fertig</span>
                )}
```

And delete the "Archivieren/Reaktivieren" button:

```tsx
                    <button type="button" onClick={toggleArchivieren} disabled={savingHeader}
                      className="px-3 py-1.5 text-sm border border-gray-200 rounded-md text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50">
                      {p.auftragFertig ? "Reaktivieren" : "Archivieren"}
                    </button>
```

(Leave the "Bearbeiten" button and the "Speichern"/"Abbrechen" buttons untouched.)

- [ ] **Step 6: Add the status field to the edit-form grid**

In the grid section below the header (`<div className="border-t border-gray-100 px-6 py-5 grid ...">`), immediately after the "Projektleiter" `<div>` block and before the "Jahr" `<div>` block, insert:

```tsx
              <div>
                <div className="text-[11px] uppercase tracking-wider text-gray-500 font-medium">Status</div>
                {editingHeader && headerForm ? (
                  <select value={headerForm.projektStatus}
                    onChange={(e) => setHeaderForm((f) => f ? { ...f, projektStatus: e.target.value } : f)}
                    className="text-[15px] text-gray-900 mt-1 border border-gray-300 rounded px-2 py-1 bg-white focus:outline-none w-full text-sm">
                    {projektStatusData?.projektStatusList.items.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                ) : (
                  <div className="mt-1 text-[15px] text-gray-900">{p.projektStatus.name}</div>
                )}
              </div>
```

- [ ] **Step 7: Type-check and build**

Run: `npm --prefix frontend run build`
Expected: no TypeScript errors (in particular, no remaining reference to `p.auftragFertig` or `auftragFertig` anywhere in this file).

Verify: `grep -n "auftragFertig\|toggleArchivieren" frontend/src/pages/ProjektDetailPage.tsx` → no output.

- [ ] **Step 8: Run the frontend test suite**

Run: `npm --prefix frontend test`
Expected: PASS, all existing tests green (no test file specifically exercises `ProjektDetailPage`'s status UI today, so this step only guards against regressions elsewhere).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/ProjektDetailPage.tsx
git commit -m "feat(frontend): Status als Dropdown im Bearbeiten-Formular der Detailseite

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Full-gate verification

**Files:** none (verification only)

- [ ] **Step 1: Run the complete pre-commit gate**

Run: `pre-commit run --all-files`
Expected: `ruff (lint)`, `ruff (format check)`, `pytest (backend)`, `mypy (type check)`, `vitest (frontend)` all pass.

- [ ] **Step 2: Confirm no leftover references**

Run: `grep -rn "auftrag_fertig\|auftragFertig" src/ tests/ frontend/src/ docs/adr/ 2>/dev/null`
Expected: no output (only this plan and the spec doc may still mention the old name historically — that's fine, they're documentation of the migration itself, not code).

- [ ] **Step 3: Manual smoke check (optional but recommended)**

Start the dev servers (`uv run python manage.py runserver` and `npm --prefix frontend run dev`), open a project's detail page, click "Bearbeiten", confirm the Status dropdown shows "Offen"/"In Arbeit"/"Fertig", change it, save, and confirm the badge in the project list reflects the new value after navigating back.
