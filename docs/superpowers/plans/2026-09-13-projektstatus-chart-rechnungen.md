# Projektstatus-Chart, Projektstatus-Spalte und Rechnungen-Pop-up — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auf der Projektdetailseite ein Chart „Projektstatus auf einen Blick" (Plan-WV / Ist-Kosten / AK verrechnet / Offen), dieselbe Kennzahl als Mini-Balken in der Projektliste, und ein Pop-up, das die Lieferantenrechnungen hinter jedem Ist-Wert zeigt.

**Architecture:** Die Rechnungs-Zuordnung bleibt vollständig im Backend: zwei neue `@graph_ql_property`-Felder (`IstWert.rechnungen` pro Kategorie, `ProjektKennzahlen.rechnungen` fürs ganze Projekt) liefern genau die Rechnungen, aus denen die jeweils angezeigte Summe gebildet wird. Im Frontend rechnet eine einzige reine Funktion (`utils/projektStatus.ts`) die Balkengeometrie aus; Chart (Detailseite) und Mini-Balken (Liste) sind zwei Darstellungen desselben Ergebnisses. Das Pop-up lädt seine Daten per `useLazyQuery` erst beim ersten Öffnen.

**Tech Stack:** Django 6 + GeneralManager 0.79.3 (Python, pytest) · React 18 + TypeScript + Apollo Client 4 + Tailwind v4 (vitest)

**Spec:** `docs/superpowers/specs/2026-09-13-projektstatus-chart-rechnungen-design.md`

## Global Constraints

- **Alle Befehle laufen im Devcontainer** dieses Worktrees:
  `devcontainer exec --workspace-folder . <befehl>`. Einmal zu Beginn
  `devcontainer up --workspace-folder .`.
- Backend-Tests: `uv run --group dev pytest <pfad>` · Frontend-Tests:
  `npm --prefix frontend test`.
- **„Erledigt" erst wenn `pre-commit run --all-files` grün ist** (ruff, pytest,
  mypy, vitest). Backend-Coverage-Gate steht auf **100 %** — jede neue Zeile
  Python braucht einen Test, der sie ausführt.
- **Niemals `git commit --no-verify`.**
- Bei jedem Task-Commit **diese Plan-Datei mit `git add`** aufnehmen (abgehakte
  Checkboxen), und beim Spec-relevanten Task auch die Spec.
- Feldzugriff im Backend immer über `self.feldname`, Related-Lookups über den
  GM (`Lieferantenrechnung.filter(...)`), nie über das rohe ORM.
- Frontend macht **keine** Validierung, keine Permission-Checks, keine
  Zugriffslogik — nur Darstellung, Queries und Server-Fehler anzeigen.
- Farben **nur** über Tokens aus `frontend/src/index.css`
  (`var(--forge-blue)` bzw. `bg-[var(--forge-blue)]`), nie Hex hartkodieren.
  Tailwind-Utilities (`bg-rose-50`, `text-gray-500`) sind wie im Bestand ok.
- Beträge über `chf()` aus `utils/format.ts`, Prozente über `pct()`.
- Branch: `projektstatus-chart-rechnungen` (existiert bereits, Spec ist
  committet).

**Verifizierte GM-Eigenheiten** (Spike gegen das echte Schema, siehe Spec):

- `@graph_ql_property` mit Rückgabe `list[Lieferantenrechnung]` erzeugt das
  GraphQL-Feld `[LieferantenrechnungType]`.
- Die Return-Annotation muss **zur Laufzeit auflösbar** sein — ein
  `TYPE_CHECKING`-Import genügt GM nicht.
- Attribut-Overrides (`rechnungen = {"read": [...]}`) wirken auch auf
  `CalculationPermission`: verweigert liefert das Feld `null`.
- `buchungskonto` ist **kein** String, sondern `KontoType` und braucht eine
  Sub-Selection `{ accountNo name }` — ohne sie antwortet der Server mit
  HTTP 400.
- `Decimal`-Felder kommen als **Float (Zahl)** an, nicht als String.

---

## File Structure

**Backend**

| Datei | Verantwortung |
| --- | --- |
| `src/apps/projekt/models/projekt_phase.py` | (aus `projekt_status.py`) Statische Liste der Projekt-Phasen |
| `src/apps/projekt/models/projekt.py` | FK `projekt_phase` statt `projekt_status` |
| `src/apps/projekt/migrations/0012_rename_projektstatus_projektphase.py` | Rename-Migration |
| `src/apps/projekt/calculation_manager/ist_wert.py` | `_rechnungen()` + `rechnungen` pro Kategorie |
| `src/apps/projekt/calculation_manager/projekt_kennzahlen.py` | `_rechnungen()` + `rechnungen` fürs Projekt |
| `src/apps/projekt/tests/test_projekt_phase.py` | (aus `test_projekt_status.py`) |
| `src/apps/projekt/tests/test_rechnungen_properties.py` | **neu** — beide Rechnungs-Properties und ihre Permissions |

**Frontend**

| Datei | Verantwortung |
| --- | --- |
| `frontend/src/index.css` | Tokens `--forge-blue-light`, `--forge-green` |
| `frontend/src/utils/projektStatus.ts` | **neu** — reine Geometrie-/Kennzahlen-Funktion |
| `frontend/src/utils/format.ts` | zusätzlich `deDate()` |
| `frontend/src/components/ProjektStatusChart.tsx` | **neu** — Karte auf der Detailseite |
| `frontend/src/components/ProjektStatusMini.tsx` | **neu** — Mini-Balken für die Liste |
| `frontend/src/components/RechnungenModal.tsx` | **neu** — Pop-up mit sortierbarer Tabelle |
| `frontend/src/graphql/queries.ts` | `GET_PROJEKT_RECHNUNGEN`, Rename der Phase-Query |
| `frontend/src/pages/ProjektDetailPage.tsx` | Chart einbauen, Ist-Zellen klickbar, Überschriften |
| `frontend/src/pages/ProjektListePage.tsx` | Spalte „Projektstatus", Spaltentitel |

---

## Task 0: `ProjektStatus` → `ProjektPhase` umbenennen

Rein mechanisch, aber breit. Muss zuerst passieren, damit der Begriff
„Projektstatus" für die neue Kennzahl frei ist. Keine Verhaltensänderung.

**Files:**
- Create: `src/apps/projekt/models/projekt_phase.py` (aus `projekt_status.py`)
- Create: `src/apps/projekt/migrations/0012_rename_projektstatus_projektphase.py`
- Create: `src/apps/projekt/tests/test_projekt_phase.py` (aus `test_projekt_status.py`)
- Delete: `src/apps/projekt/models/projekt_status.py`, `src/apps/projekt/tests/test_projekt_status.py`
- Modify: `src/apps/projekt/models/__init__.py`, `src/apps/projekt/models/projekt.py`,
  `src/apps/projekt/admin.py`, `conftest.py`, `src/forge/graphql_metric_operations.py`,
  `src/apps/projekt/tests/{test_projekt,test_kosten_position,test_projekt_kennzahlen,test_ist_wert,test_permissions_graphql}.py`,
  `tests/test_graphql_queries.py`, `tests/test_graphql_mutations.py`,
  `docs/specs/projekt.md`
- Modify (Frontend): `frontend/src/graphql/{queries,mutations}.ts`,
  `frontend/src/pages/{ProjektListePage,ProjektDetailPage,ProjektNeuPage}.tsx`
  und die drei zugehörigen `.test.tsx`

**Interfaces:**
- Consumes: —
- Produces: Manager `ProjektPhase` (Felder `id`, `name`, `is_active`,
  `projekte_list`); `Projekt.projekt_phase: ProjektPhase`; GraphQL
  `projekt { projektPhase { id name } }`, `projektPhaseList`,
  Mutations-Argument `projektPhase: ID`. Frontend-Export
  `GET_PROJEKT_PHASE_IDS` (Operation `ProjektPhaseIds`).

- [x] **Step 1: Modelldatei umbenennen und Klasse anpassen**

```bash
git mv src/apps/projekt/models/projekt_status.py src/apps/projekt/models/projekt_phase.py
git mv src/apps/projekt/tests/test_projekt_status.py src/apps/projekt/tests/test_projekt_phase.py
```

`src/apps/projekt/models/projekt_phase.py` — nur diese Stellen ändern
(Klassenname, Docstring, `verbose_name`, `db_table`):

```python
class ProjektPhase(GeneralManager):
    """Statische Liste der Projekt-Phasen (Offen, In Arbeit, Fertig)."""

    _data = [
        {"id": 1, "name": "Offen", "is_active": True},
        {"id": 2, "name": "In Arbeit", "is_active": True},
        {"id": 3, "name": "Fertig", "is_active": True},
    ]

    id: int
    is_active: bool
    name: str

    projekte_list: Bucket[Projekt]

    def __str__(self) -> str:
        return self.name

    class Interface(ReadOnlyInterface):
        is_active = models.BooleanField(default=True)
        name = models.CharField(max_length=50, unique=True)

        class Meta:
            verbose_name = "Projekt-Phase"
            verbose_name_plural = "Projekt-Phasen"
            db_table = "projekt_projektphase"
            ordering = ["id"]

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["isAdmin"]
        __update__ = ["isAdmin"]
        __delete__ = ["isAdmin"]
```

`src/apps/projekt/models/__init__.py`:

```python
from __future__ import annotations

from .kosten_position import KostenPosition
from .kostenart import Kostenart
from .projekt import Projekt
from .projekt_phase import ProjektPhase

__all__ = ["Projekt", "KostenPosition", "Kostenart", "ProjektPhase"]
```

In `src/apps/projekt/models/projekt.py` vier Stellen: Import
(`from apps.projekt.models.projekt_phase import ProjektPhase`), Annotation
(`projekt_phase: ProjektPhase`), Feld (`projekt_phase = models.ForeignKey("projekt.ProjektPhase", on_delete=models.PROTECT, related_name="projekte")`).

- [x] **Step 2: Restliche Backend-Referenzen umschreiben**

```bash
grep -rl "ProjektStatus\|projekt_status" \
  src tests conftest.py docs/specs \
  --exclude-dir=__pycache__ --exclude-dir=migrations \
| xargs sed -i 's/ProjektStatus/ProjektPhase/g; s/projekt_status/projekt_phase/g'
```

Danach von Hand nachziehen, was die Ersetzung nicht trifft:

- `conftest.py`: Fixture-Name `_seed_projekt_status` → `_seed_projekt_phase`,
  Docstring („die drei ProjektPhase-Einträge", „Projekt.create() braucht
  `ProjektPhase.filter(name="Offen")`").
- `src/forge/graphql_metric_operations.py`: Eintrag `"ProjektStatusIds"` →
  `"ProjektPhaseIds"` (Liste bleibt alphabetisch sortiert).
- `docs/specs/projekt.md`: Zeile 50 (Feldname + Beschreibung „Lifecycle-Phase")
  und der Listen-Mockup ab Zeile 215 (Spaltentitel `Status` → `Phase`).
- `src/apps/projekt/tests/test_projekt_phase.py`: Docstring/Testnamen.

- [x] **Step 3: Migration schreiben**

`src/apps/projekt/migrations/0012_rename_projektstatus_projektphase.py`:

```python
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("projekt", "0011_alter_historicalkostenposition_art_and_more"),
    ]

    operations = [
        migrations.RenameModel(old_name="ProjektStatus", new_name="ProjektPhase"),
        migrations.RenameModel(
            old_name="HistoricalProjektStatus", new_name="HistoricalProjektPhase"
        ),
        migrations.AlterModelTable(
            name="projektphase", table="projekt_projektphase"
        ),
        migrations.AlterModelOptions(
            name="projektphase",
            options={
                "ordering": ["id"],
                "verbose_name": "Projekt-Phase",
                "verbose_name_plural": "Projekt-Phasen",
            },
        ),
        migrations.RenameField(
            model_name="projekt", old_name="projekt_status", new_name="projekt_phase"
        ),
        migrations.RenameField(
            model_name="historicalprojekt",
            old_name="projekt_status",
            new_name="projekt_phase",
        ),
    ]
```

- [x] **Step 4: Migration gegen die Modelle prüfen**

Run: `devcontainer exec --workspace-folder . uv run python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`.

Meldet Django noch Änderungen, zeigt die Ausgabe welche Operation fehlt
(typisch: eine vergessene `AlterModelOptions` für das Historical-Modell) —
diese Operation ergänzen und erneut prüfen. **Nicht** `makemigrations` ohne
`--check` laufen lassen: Django fragt bei Renames interaktiv nach und legt
sonst Delete+Create an, was die Daten verlöre.

- [x] **Step 5: Frontend-Referenzen umschreiben**

```bash
grep -rl "projektStatus\|ProjektStatus\|PROJEKT_STATUS" frontend/src \
| xargs sed -i 's/projektStatusList/projektPhaseList/g; s/projektStatus/projektPhase/g; s/ProjektStatusIds/ProjektPhaseIds/g; s/ProjektStatusOption/ProjektPhaseOption/g; s/ProjektStatusData/ProjektPhaseData/g; s/ProjektStatusIdItem/ProjektPhaseIdItem/g; s/ProjektStatusIdsData/ProjektPhaseIdsData/g; s/GET_PROJEKT_STATUS_IDS/GET_PROJEKT_PHASE_IDS/g'
```

Danach die sichtbaren Beschriftungen von Hand — `sed` darf sie nicht treffen,
weil „Status" auch anderswo steht:

- `ProjektListePage.tsx`: Spaltenkopf `Status` → `Phase` (die `<th>` ganz
  rechts, aktuell Zeile 381). `StatusBadge`, `STATUS_STYLES`, `STATUS_DOTS`
  behalten ihre Namen — sie beschreiben die Badge, nicht das Feld.
- `ProjektDetailPage.tsx`: Header-Label `Status` → `Phase` (aktuell Zeile 564).
- `ProjektNeuPage.tsx`: Label `Status *` → `Phase *`, Fehlertext
  „Bitte einen Status auswählen." → „Bitte eine Phase auswählen.",
  `htmlFor`/`id`/`name` `projektStatus` → `projektPhase` (erledigt `sed`),
  Kommentar „Statusliste" → „Phasenliste".
- In den drei `.test.tsx`: `ProjektListePage.test.tsx` prüft den Spaltenkopf
  `"Status"` → auf `"Phase"` ändern; `ProjektNeuPage.test.tsx` prüft das Label
  `"Status *"` und den Fehlertext `"Bitte einen Status auswählen."` → auf
  `"Phase *"` bzw. `"Bitte eine Phase auswählen."` ändern;
  `ProjektDetailPage.test.tsx` prüft das Header-Label `"Status"` → `"Phase"`.
  Die Mock-Daten selbst hat `sed` bereits umgestellt (`projektPhase`,
  `projektPhaseList`).

- [x] **Step 6: Volles Gate**

Run: `devcontainer exec --workspace-folder . uv run pre-commit run --all-files`
Expected: ruff, pytest, mypy, vitest alle **Passed**.

Häufigster Fehler an dieser Stelle: eine Teststelle, die den GraphQL-Query-Text
als String enthält (`tests/test_graphql_*.py`) und noch `projektStatus` schreibt
— der Server antwortet dann mit `errors` statt `data`.

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: ProjektStatus zu ProjektPhase umbenannt

Macht den Begriff Projektstatus frei für die neue Finanzkennzahl
(Plan-WV, Ist-Kosten, AK verrechnet, Offen).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Wn4HSteRch4Z7TwLgvAoQ3"
```

---

## Task 1: Backend — `IstWert.rechnungen`

**Files:**
- Modify: `src/apps/projekt/calculation_manager/ist_wert.py`
- Test: `src/apps/projekt/tests/test_rechnungen_properties.py` (neu)

**Interfaces:**
- Consumes: `ProjektPhase` aus Task 0.
- Produces: `IstWert._rechnungen() -> tuple[Lieferantenrechnung, ...]` (privat)
  und `IstWert.rechnungen -> list[Lieferantenrechnung]`, im Schema
  `istWertList { items { rechnungen { ... } } }`.

- [x] **Step 1: Failing Test schreiben**

`src/apps/projekt/tests/test_rechnungen_properties.py`:

```python
"""Rechnungslisten hinter den Ist-Werten (IstWert.rechnungen,
ProjektKennzahlen.rechnungen)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.test import TestCase
from general_manager.measurement import Measurement

from apps.bexio.models import Konto, Lieferantenrechnung
from apps.projekt.calculation_manager import IstWert
from apps.projekt.models import Kostenart, Projekt, ProjektPhase

_KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]
_KontoModel: Any = Konto.Interface._model  # type: ignore[misc]
_LieferantenrechnungModel: Any = Lieferantenrechnung.Interface._model  # type: ignore[misc]

_TESTJAHR = 2024
_AUFTRAGSNUMMER = "2024-300"


def _lade_kostenart_daten() -> None:
    _KostenartModel.objects.bulk_create(
        [_KostenartModel(**item) for item in Kostenart._data],
        ignore_conflicts=True,
    )


def _konto(account_no: str) -> Any:
    return _KontoModel.objects.create(
        bexio_id=uuid.uuid4(),
        bexio_int_id=hash(account_no) % 100000,
        account_no=account_no,
        name=f"Konto {account_no}",
    )


def _rechnung(
    richtiger_titel: str,
    betrag: Decimal,
    steuer: Decimal = Decimal("0"),
    konto_model: Any = None,
    dokument_nr: str | None = None,
) -> None:
    _LieferantenrechnungModel.objects.create(
        bexio_id=uuid.uuid4(),
        bexio_zeilen_id=uuid.uuid4(),
        dokument_nr=dokument_nr or f"R-{uuid.uuid4().hex[:6]}",
        titel="Testrechnung",
        richtiger_titel=richtiger_titel,
        status="paid",
        rechnungsdatum=date(2024, 1, 15),
        lieferant_id=1,
        firmenname="Lieferant AG",
        waehrung_code="CHF",
        rechnungsbetrag=betrag,
        ausstehender_betrag=Decimal("0"),
        bexio_erstellt_am=datetime(2024, 1, 15, 10, 0, 0, tzinfo=None),
        betrag=betrag,
        steuer_berechnet=steuer,
        buchungskonto=konto_model,
    )


class RechnungenBasis(TestCase):
    def setUp(self) -> None:
        _lade_kostenart_daten()
        offen = ProjektPhase.filter(name="Offen").first()
        assert offen is not None
        self.projekt = Projekt.create(
            ignore_permission=True,
            name="Rechnungs-Projekt",
            auftragsnummer=_AUFTRAGSNUMMER,
            jahr=_TESTJAHR,
            offerte_summe=Measurement(Decimal("100000"), "CHF"),
            projekt_phase=offen,
        )
        self.konto_4001 = _konto("4001")

    def _iw(self, schluessel: str) -> IstWert:
        art = Kostenart.filter(schluessel=schluessel).first()
        assert isinstance(art, Kostenart)
        return IstWert(projekt=self.projekt, kostenart=art)


class IstWertRechnungenTest(RechnungenBasis):
    """IstWert.rechnungen liefert genau die Rechnungen hinter ist_kosten_wert."""

    def test_leer_ohne_passende_rechnung(self) -> None:
        self.assertEqual(self._iw("apparate").rechnungen, [])

    def test_leer_fuer_ertragsblock(self) -> None:
        _rechnung(_AUFTRAGSNUMMER, Decimal("1000"), Decimal("0"), self.konto_4001)
        self.assertEqual(self._iw("regie").rechnungen, [])

    def test_leer_fuer_stunden(self) -> None:
        self.assertEqual(self._iw("stunden").rechnungen, [])

    def test_leer_fuer_transport_montage(self) -> None:
        konto_44401 = _konto("44401")
        _rechnung(_AUFTRAGSNUMMER, Decimal("1000"), Decimal("0"), konto_44401)
        self.assertEqual(self._iw("transport_montage").rechnungen, [])

    def test_leer_ohne_konto_nummer(self) -> None:
        self.assertEqual(self._iw("nachtrag").rechnungen, [])

    def test_konto_match(self) -> None:
        _rechnung(
            _AUFTRAGSNUMMER, Decimal("1000"), Decimal("77"), self.konto_4001, "R-1"
        )
        rechnungen = self._iw("apparate").rechnungen
        self.assertEqual([r.dokument_nr for r in rechnungen], ["R-1"])

    def test_ignoriert_anderes_projekt(self) -> None:
        _rechnung("ANDERES", Decimal("500"), Decimal("0"), self.konto_4001)
        self.assertEqual(self._iw("apparate").rechnungen, [])

    def test_diverses_enthaelt_unbekannte_und_kontolose(self) -> None:
        unbekannt = _konto("9999")
        _rechnung(_AUFTRAGSNUMMER, Decimal("400"), Decimal("0"), unbekannt, "R-U")
        _rechnung(_AUFTRAGSNUMMER, Decimal("200"), Decimal("0"), None, "R-O")
        _rechnung(_AUFTRAGSNUMMER, Decimal("999"), Decimal("0"), self.konto_4001, "R-K")
        nummern = sorted(r.dokument_nr for r in self._iw("diverses").rechnungen)
        self.assertEqual(nummern, ["R-O", "R-U"])

    def test_summe_der_liste_entspricht_ist_kosten_wert(self) -> None:
        _rechnung(_AUFTRAGSNUMMER, Decimal("500"), Decimal("0"), self.konto_4001)
        _rechnung(_AUFTRAGSNUMMER, Decimal("300"), Decimal("23.1"), self.konto_4001)
        iw = self._iw("apparate")
        summe = sum(
            (r.betrag - r.steuer_berechnet for r in iw.rechnungen), Decimal("0")
        )
        assert iw.ist_kosten_wert is not None
        self.assertEqual(Decimal(iw.ist_kosten_wert.magnitude), summe)
```

- [x] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/projekt/tests/test_rechnungen_properties.py -v --no-cov`
Expected: FAIL — `AttributeError: 'IstWert' object has no attribute 'rechnungen'`

- [x] **Step 3: Implementieren**

In `src/apps/projekt/calculation_manager/ist_wert.py` die Auswahl-Logik aus
`ist_kosten_wert` in einen Helfer ziehen und beide Properties darauf stützen.
`_rechnungen_nach_konto` und `ist_kosten_wert_prozent` bleiben unverändert.

```python
    @cached
    def _rechnungen(self) -> tuple[Lieferantenrechnung, ...]:
        """Die Rechnungen, aus denen ist_kosten_wert gebildet wird."""
        if self.kostenart.ist_ertragsblock:
            return ()
        if self.kostenart.schluessel in ("stunden", "transport_montage"):
            return ()  # TODO stunden.md

        index = self._rechnungen_nach_konto()

        if self.kostenart.schluessel == "diverses":
            bekannte = frozenset(
                str(k.konto_nummer)
                for k in Kostenart.all()
                if k.konto_nummer is not None
            )
            return tuple(
                r
                for key, gruppe in index.items()
                if key is None or key not in bekannte
                for r in gruppe
            )

        konto_nr = self.kostenart.konto_nummer
        if konto_nr is None:
            return ()
        return tuple(index.get(str(konto_nr), ()))

    @graph_ql_property
    def rechnungen(self) -> list[Lieferantenrechnung]:
        return list(self._rechnungen())

    @graph_ql_property
    def ist_kosten_wert(self) -> Measurement | None:
        rechnungen = self._rechnungen()
        if not rechnungen:
            return None
        summe = sum((r.betrag - r.steuer_berechnet for r in rechnungen), Decimal("0"))
        return Measurement(summe, "CHF")
```

Die alte `ist_kosten_wert` (mit der inline-Auswahl) wird dabei vollständig
ersetzt.

- [x] **Step 4: Tests laufen lassen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/projekt/tests/test_rechnungen_properties.py src/apps/projekt/tests/test_ist_wert.py -v --no-cov`
Expected: PASS (alle, auch die bestehenden `test_ist_wert.py` — das Verhalten
von `ist_kosten_wert` ändert sich nicht).

- [x] **Step 5: Commit**

```bash
git add src/apps/projekt/calculation_manager/ist_wert.py \
        src/apps/projekt/tests/test_rechnungen_properties.py \
        docs/superpowers/plans/2026-09-13-projektstatus-chart-rechnungen.md
git commit -m "feat(projekt): IstWert.rechnungen liefert die Rechnungen je Kategorie

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Wn4HSteRch4Z7TwLgvAoQ3"
```

---

## Task 2: Backend — `ProjektKennzahlen.rechnungen` samt Permission

**Files:**
- Modify: `src/apps/projekt/calculation_manager/projekt_kennzahlen.py`
- Test: `src/apps/projekt/tests/test_rechnungen_properties.py` (erweitern)

**Interfaces:**
- Consumes: Testhelfer `_rechnung`, `_konto`, `RechnungenBasis` aus Task 1.
- Produces: `ProjektKennzahlen.rechnungen -> list[Lieferantenrechnung]`, im
  Schema `projektKennzahlenList { items { rechnungen { ... } } }`; für
  Betrachter `null`.

- [x] **Step 1: Failing Tests schreiben**

An `src/apps/projekt/tests/test_rechnungen_properties.py` anhängen:

```python
class ProjektKennzahlenRechnungenTest(RechnungenBasis):
    """ProjektKennzahlen.rechnungen = alle Rechnungen des Projekts."""

    def _kennzahlen(self) -> Any:
        from apps.projekt.calculation_manager import ProjektKennzahlen

        return ProjektKennzahlen(projekt=self.projekt)

    def test_leer_ohne_rechnungen(self) -> None:
        self.assertEqual(self._kennzahlen().rechnungen, [])

    def test_enthaelt_alle_konten_auch_ohne_kategorie(self) -> None:
        konto_44401 = _konto("44401")
        _rechnung(_AUFTRAGSNUMMER, Decimal("100"), Decimal("0"), self.konto_4001, "R-A")
        _rechnung(_AUFTRAGSNUMMER, Decimal("200"), Decimal("0"), konto_44401, "R-T")
        _rechnung(_AUFTRAGSNUMMER, Decimal("300"), Decimal("0"), None, "R-O")
        nummern = sorted(r.dokument_nr for r in self._kennzahlen().rechnungen)
        self.assertEqual(nummern, ["R-A", "R-O", "R-T"])

    def test_ignoriert_anderes_projekt(self) -> None:
        _rechnung("ANDERES", Decimal("500"), Decimal("0"), self.konto_4001)
        self.assertEqual(self._kennzahlen().rechnungen, [])

    def test_summe_der_liste_entspricht_summe_ist_kosten(self) -> None:
        _rechnung(_AUFTRAGSNUMMER, Decimal("500"), Decimal("38.5"), self.konto_4001)
        _rechnung(_AUFTRAGSNUMMER, Decimal("300"), Decimal("0"), None)
        kennzahlen = self._kennzahlen()
        summe = sum(
            (r.betrag - r.steuer_berechnet for r in kennzahlen.rechnungen),
            Decimal("0"),
        )
        self.assertEqual(Decimal(kennzahlen.summe_ist_kosten.magnitude), summe)
```

Und die Permission-Prüfung über GraphQL — sie ist der eigentliche Grund für den
Attribut-Override:

```python
RECHNUNGEN_QUERY = """
query {
  projektKennzahlenList {
    items {
      rechnungen { dokumentNr nettoBetrag buchungskonto { accountNo name } }
    }
  }
}
"""


class RechnungenPermissionTest(RollenGraphQLTestBase):
    """Betrachter darf Rechnungen nicht sehen, Projektleiter schon."""

    def _rechnungen(self) -> Any:
        items = self._gql(RECHNUNGEN_QUERY)["projektKennzahlenList"]["items"]
        return items[0]["rechnungen"] if items else None

    def test_betrachter_sieht_keine_rechnungen(self) -> None:
        self._login("Betrachter")
        self.assertIsNone(self._rechnungen())

    def test_projektleiter_sieht_rechnungen(self) -> None:
        self._login("Projektleiter")
        self.assertEqual(self._rechnungen(), [])

    def test_admin_sieht_rechnungen(self) -> None:
        self._login("Admin")
        self.assertEqual(self._rechnungen(), [])
```

Dafür oben im Modul ergänzen:

```python
from apps.projekt.tests.test_permissions_graphql import RollenGraphQLTestBase
```

- [x] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/projekt/tests/test_rechnungen_properties.py -v --no-cov`
Expected: FAIL — `Cannot query field 'rechnungen' on type 'ProjektKennzahlenType'`
bzw. `AttributeError: 'ProjektKennzahlen' object has no attribute 'rechnungen'`

- [x] **Step 3: Implementieren**

In `src/apps/projekt/calculation_manager/projekt_kennzahlen.py`:

```python
    class Permission(CalculationPermission):
        __read__ = ["isForgeAdmin", "isProjektleiter", "isBetrachter"]
        # Lieferantenrechnungen sind für Betrachter tabu (siehe 5180928);
        # __read__ dieses Managers ist weiter gefasst, deshalb der Override.
        rechnungen = {"read": ["isForgeAdmin", "isProjektleiter"]}

    @cached
    def _rechnungen(self) -> tuple[Lieferantenrechnung, ...]:
        return tuple(
            Lieferantenrechnung.filter(richtiger_titel=self.projekt.auftragsnummer)
        )

    @graph_ql_property
    def rechnungen(self) -> list[Lieferantenrechnung]:
        return list(self._rechnungen())

    @cached
    def _summe_ist(self) -> Decimal:
        rechnungen = self._rechnungen()
        if not rechnungen:
            return Decimal("0")
        return sum(
            (r.betrag - r.steuer_berechnet for r in rechnungen), Decimal("0")
        ).quantize(Decimal("0.01"))
```

(`_summe_ist` ersetzt die bisherige Fassung, die dieselbe Query selbst
abgesetzt hat — damit sind Liste und Summe garantiert dieselbe Menge.)

- [x] **Step 4: Tests laufen lassen**

Run: `devcontainer exec --workspace-folder . uv run --group dev pytest src/apps/projekt/tests/ -v --no-cov`
Expected: PASS — insbesondere auch `test_projekt_kennzahlen.py` und
`test_permissions_graphql.py` unverändert grün.

- [x] **Step 5: Volles Gate**

Run: `devcontainer exec --workspace-folder . uv run pre-commit run --all-files`
Expected: alle Hooks **Passed** (Coverage-Gate 100 % — die neuen Zeilen sind
durch die Tests oben abgedeckt).

- [x] **Step 6: Commit**

```bash
git add src/apps/projekt/calculation_manager/projekt_kennzahlen.py \
        src/apps/projekt/tests/test_rechnungen_properties.py \
        docs/superpowers/plans/2026-09-13-projektstatus-chart-rechnungen.md
git commit -m "feat(projekt): ProjektKennzahlen.rechnungen, für Betrachter gesperrt

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Wn4HSteRch4Z7TwLgvAoQ3"
```

---

## Task 3: Frontend — Tokens und Rechenfunktion `projektStatus.ts`

Reine Logik, keine Darstellung. Treibt Chart (Task 4) und Mini-Balken (Task 5).

**Files:**
- Modify: `frontend/src/index.css`
- Create: `frontend/src/utils/projektStatus.ts`
- Test: `frontend/src/utils/projektStatus.test.ts` (neu)

**Interfaces:**
- Consumes: —
- Produces: `getProjektStatus(input: ProjektStatusInput): ProjektStatusResult | null`
  mit den unten definierten Typen; CSS-Variablen `--forge-blue-light`,
  `--forge-green`.

- [x] **Step 1: Failing Test schreiben**

`frontend/src/utils/projektStatus.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { getProjektStatus } from "./projektStatus";

describe("getProjektStatus", () => {
  it("gibt null ohne Plan-WV", () => {
    expect(getProjektStatus({ planWV: null, sollWV: null, ist: 100, ak: 0 })).toBeNull();
  });

  it("gibt null bei Plan-WV 0", () => {
    expect(getProjektStatus({ planWV: 0, sollWV: 0, ist: 100, ak: 0 })).toBeNull();
  });

  it("Normalfall: hellblau bis Soll, dunkelblau bis Plan", () => {
    const r = getProjektStatus({ planWV: 250000, sollWV: 230000, ist: 168400, ak: 120000 })!;
    expect(r.scale).toBe(250000);
    expect(r.sollLight).toEqual({ from: 0, to: 92 });
    expect(r.fillDark).toEqual({ from: 92, to: 100 });
    expect(r.sollGhost).toBeNull();
    expect(r.overrun).toBeNull();
    expect(r.offen).toBe(130000);
    expect(r.offenPct).toBeCloseTo(52, 5);
    expect(r.istOverPlan).toBe(false);
  });

  it("Soll gleich Plan: alles hellblau, keine Auffüllung", () => {
    const r = getProjektStatus({ planWV: 250000, sollWV: 250000, ist: 168400, ak: 0 })!;
    expect(r.sollLight).toEqual({ from: 0, to: 100 });
    expect(r.fillDark).toBeNull();
    expect(r.offen).toBe(250000);
    expect(r.offenPct).toBe(100);
  });

  it("Ist über Plan: Massstab waechst, Ueberschreitung als eigenes Segment", () => {
    const r = getProjektStatus({ planWV: 250000, sollWV: 230000, ist: 290000, ak: 120000 })!;
    expect(r.scale).toBe(290000);
    expect(r.istPct).toBe(100);
    expect(r.planPct).toBeCloseTo(86.2069, 3);
    expect(r.overrun!.from).toBeCloseTo(86.2069, 3);
    expect(r.overrun!.to).toBe(100);
    expect(r.istOverPlan).toBe(true);
    expect(r.istOverPlanAbs).toBe(40000);
    expect(r.istOverPlanPct).toBeCloseTo(16, 5);
  });

  it("AK groesser als Plan wird gedeckelt", () => {
    const r = getProjektStatus({ planWV: 250000, sollWV: 250000, ist: 168400, ak: 260000 })!;
    expect(r.akCapped).toBe(true);
    expect(r.akPct).toBe(100);
    expect(r.offen).toBe(0);
    expect(r.offenPct).toBe(0);
  });

  it("Plan kleiner als Soll: dunkelblau bis Plan, Ueberhang gestrichelt", () => {
    const r = getProjektStatus({ planWV: 220000, sollWV: 250000, ist: 168400, ak: 120000 })!;
    expect(r.scale).toBe(250000);
    expect(r.sollLight).toBeNull();
    expect(r.fillDark).toEqual({ from: 0, to: 88 });
    expect(r.sollGhost).toEqual({ from: 88, to: 100 });
    expect(r.offen).toBe(100000);
    expect(r.offenPct).toBeCloseTo(45.4545, 3);
  });

  it("ohne Soll-WV gilt Soll gleich Plan", () => {
    const r = getProjektStatus({ planWV: 100000, sollWV: null, ist: 0, ak: 0 })!;
    expect(r.sollLight).toEqual({ from: 0, to: 100 });
    expect(r.fillDark).toBeNull();
  });
});
```

- [x] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run projektStatus`
Expected: FAIL — `Failed to resolve import "./projektStatus"`

- [x] **Step 3: Implementieren**

`frontend/src/utils/projektStatus.ts`:

```ts
export type ProjektStatusInput = {
  /** Plan-WV in CHF; ohne ihn gibt es kein Chart. */
  planWV: number | null;
  /** Soll-WV in CHF; null => gleich Plan-WV. */
  sollWV: number | null;
  /** Kumulierte Ist-Kosten in CHF. */
  ist: number;
  /** Bisher verrechnete A-Konto-Zahlungen in CHF. */
  ak: number;
};

/** Balkenabschnitt in Prozent der Chart-Breite. */
export type Segment = { from: number; to: number };

export type ProjektStatusResult = {
  /** Bezugsgroesse der Balkenbreite: max(Plan, Soll, Ist). */
  scale: number;
  planPct: number;
  /** Hellblau: 0 bis Soll-WV (nur wenn Plan >= Soll). */
  sollLight: Segment | null;
  /** Dunkelblau: Auffuellung bis Plan-WV. */
  fillDark: Segment | null;
  /** Hellblau gestrichelt: Soll-Ueberhang (nur wenn Soll > Plan). */
  sollGhost: Segment | null;
  /** Rot gestrichelt: Plan bis Ist (nur wenn Ist > Plan). */
  overrun: Segment | null;
  istPct: number;
  istOverPlan: boolean;
  istOverPlanAbs: number;
  istOverPlanPct: number;
  /** AK-Balken, auf Plan-WV gedeckelt. */
  akPct: number;
  akCapped: boolean;
  offen: number;
  offenPct: number;
};

export function getProjektStatus(
  input: ProjektStatusInput,
): ProjektStatusResult | null {
  const { planWV, ist, ak } = input;
  if (planWV == null || planWV <= 0) return null;

  const sollWV = input.sollWV ?? planWV;
  const scale = Math.max(planWV, sollWV, ist);
  const toPct = (value: number): number => (value / scale) * 100;

  const planAbSoll = planWV >= sollWV;
  const sollLight =
    planAbSoll && sollWV > 0 ? { from: 0, to: toPct(sollWV) } : null;
  const fillDark = planAbSoll
    ? planWV > sollWV
      ? { from: toPct(sollWV), to: toPct(planWV) }
      : null
    : { from: 0, to: toPct(planWV) };
  const sollGhost = planAbSoll
    ? null
    : { from: toPct(planWV), to: toPct(sollWV) };

  const istOverPlan = ist > planWV;
  const akEffektiv = Math.min(ak, planWV);

  return {
    scale,
    planPct: toPct(planWV),
    sollLight,
    fillDark,
    sollGhost,
    overrun: istOverPlan ? { from: toPct(planWV), to: toPct(ist) } : null,
    istPct: toPct(ist),
    istOverPlan,
    istOverPlanAbs: istOverPlan ? ist - planWV : 0,
    istOverPlanPct: istOverPlan ? ((ist - planWV) / planWV) * 100 : 0,
    akPct: toPct(akEffektiv),
    akCapped: ak > planWV,
    offen: planWV - akEffektiv,
    offenPct: ((planWV - akEffektiv) / planWV) * 100,
  };
}
```

- [x] **Step 4: Test laufen lassen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run projektStatus`
Expected: PASS (8 Tests)

- [x] **Step 5: Tokens ergänzen**

In `frontend/src/index.css` im `:root`-Block, direkt nach `--forge-red-soft`:

```css
  --forge-blue-light: #93A7FA;
  --forge-green: #059669;
```

- [x] **Step 6: Commit**

```bash
git add frontend/src/utils/projektStatus.ts \
        frontend/src/utils/projektStatus.test.ts \
        frontend/src/index.css \
        docs/superpowers/plans/2026-09-13-projektstatus-chart-rechnungen.md
git commit -m "feat(frontend): Rechenfunktion und Tokens für den Projektstatus

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Wn4HSteRch4Z7TwLgvAoQ3"
```

---

## Task 4: Frontend — Chart auf der Projektdetailseite

**Files:**
- Create: `frontend/src/components/ProjektStatusChart.tsx`
- Test: `frontend/src/components/ProjektStatusChart.test.tsx` (neu)
- Modify: `frontend/src/pages/ProjektDetailPage.tsx` (Zeilen 198, 636, 861)
- Modify: `frontend/src/pages/ProjektDetailPage.test.tsx`

**Interfaces:**
- Consumes: `getProjektStatus`, `Segment` aus Task 3; `chf`, `pct` aus
  `utils/format.ts`.
- Produces: `<ProjektStatusChart planWV sollWV ist ak />` (Default-Export).

- [x] **Step 1: Failing Test schreiben**

`frontend/src/components/ProjektStatusChart.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ProjektStatusChart from "./ProjektStatusChart";

afterEach(cleanup);

describe("ProjektStatusChart", () => {
  it("zeigt Titel, die drei Linien und den offenen Betrag", () => {
    render(<ProjektStatusChart planWV={250000} sollWV={230000} ist={168400} ak={120000} />);
    expect(screen.getByText("Projektstatus auf einen Blick")).toBeInTheDocument();
    expect(screen.getByText("Plan-WV")).toBeInTheDocument();
    // "Ist-Kosten kum." und "AK verrechnet" stehen zweimal: Legende + Zeilen-Label.
    expect(screen.getAllByText("Ist-Kosten kum.")).toHaveLength(2);
    expect(screen.getAllByText("AK verrechnet")).toHaveLength(2);
    expect(screen.getByText("CHF 130'000.00")).toBeInTheDocument();
    expect(screen.getByText("52.0 % von Plan-WV")).toBeInTheDocument();
  });

  it("markiert Ist über Plan-WV", () => {
    render(<ProjektStatusChart planWV={250000} sollWV={230000} ist={290000} ak={120000} />);
    expect(screen.getByTestId("ist-wert")).toHaveTextContent("⚠");
    expect(
      screen.getByText("Ist über Plan-WV: +CHF 40'000.00 (+16.0 %)"),
    ).toBeInTheDocument();
  });

  it("weist gedeckelte AK-Werte aus", () => {
    render(<ProjektStatusChart planWV={250000} sollWV={250000} ist={100} ak={260000} />);
    expect(screen.getByText("gedeckelt")).toBeInTheDocument();
    expect(screen.getByText("CHF 0.00")).toBeInTheDocument();
  });

  it("zeigt einen Hinweis ohne Plan-WV", () => {
    render(<ProjektStatusChart planWV={null} sollWV={null} ist={0} ak={0} />);
    expect(
      screen.getByText("Keine WV-Summe erfasst — Plan-WV fehlt."),
    ).toBeInTheDocument();
    // Ohne Plan-WV weder Legende noch Linien.
    expect(screen.queryAllByText("AK verrechnet")).toHaveLength(0);
  });
});
```

- [x] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run ProjektStatusChart`
Expected: FAIL — `Failed to resolve import "./ProjektStatusChart"`

- [x] **Step 3: Komponente implementieren**

`frontend/src/components/ProjektStatusChart.tsx`:

```tsx
import { chf } from "../utils/format";
import { getProjektStatus, type Segment } from "../utils/projektStatus";

type Props = {
  planWV: number | null;
  sollWV: number | null;
  ist: number;
  ak: number;
};

const GESTRICHELT_ROT =
  "repeating-linear-gradient(90deg, var(--forge-red) 0 6px, transparent 6px 10px)";
const GESTRICHELT_HELLBLAU =
  "repeating-linear-gradient(90deg, var(--forge-blue-light) 0 6px, transparent 6px 10px)";

function Seg({
  seg,
  style,
}: {
  seg: Segment | null;
  style: React.CSSProperties;
}) {
  if (!seg) return null;
  return (
    <div
      className="absolute top-0 h-full"
      style={{ left: `${seg.from}%`, width: `${seg.to - seg.from}%`, ...style }}
    />
  );
}

function LegendItem({ label, style }: { label: string; style: React.CSSProperties }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="w-3.5 h-2 rounded-sm shrink-0" style={style} />
      {label}
    </span>
  );
}

function Row({
  label,
  value,
  children,
}: {
  label: string;
  value: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      className="grid items-center gap-3"
      style={{ gridTemplateColumns: "120px 1fr 150px" }}
    >
      <span className="text-[10px] uppercase tracking-wider font-semibold text-gray-500">
        {label}
      </span>
      <div className="relative h-2.5 rounded-sm bg-gray-100">{children}</div>
      <span className="text-right text-[12px] tabular-nums">{value}</span>
    </div>
  );
}

export default function ProjektStatusChart({ planWV, sollWV, ist, ak }: Props) {
  const status = getProjektStatus({ planWV, sollWV, ist, ak });

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm mt-5">
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-[15px] font-semibold text-gray-900">
          Projektstatus auf einen Blick
        </h2>
        {status && (
          <div className="flex items-center gap-3 text-[11px] text-gray-500 flex-wrap">
            <LegendItem
              label="Soll-WV"
              style={{ backgroundColor: "var(--forge-blue-light)" }}
            />
            <LegendItem
              label="Auffüllung bis Plan-WV"
              style={{ backgroundColor: "var(--forge-blue)" }}
            />
            <LegendItem
              label="Ist-Kosten kum."
              style={{ backgroundColor: "var(--forge-red)" }}
            />
            <LegendItem
              label="AK verrechnet"
              style={{ backgroundColor: "var(--forge-green)" }}
            />
            <LegendItem label="Überschreitung Plan-WV" style={{ background: GESTRICHELT_ROT }} />
          </div>
        )}
      </div>

      {!status ? (
        <p className="px-6 py-4 text-[13px] italic text-gray-500">
          Keine WV-Summe erfasst — Plan-WV fehlt.
        </p>
      ) : (
        <div
          className="px-6 py-4 grid gap-6 items-center"
          style={{ gridTemplateColumns: "minmax(0, 1fr) 200px" }}
        >
          <div className="flex flex-col gap-3">
            <Row
              label="Plan-WV"
              value={
                <span className="font-semibold text-gray-900">{chf(planWV)}</span>
              }
            >
              <Seg
                seg={status.sollLight}
                style={{
                  backgroundColor: "var(--forge-blue-light)",
                  borderRadius: "3px 0 0 3px",
                }}
              />
              <Seg seg={status.fillDark} style={{ backgroundColor: "var(--forge-blue)" }} />
              <Seg seg={status.sollGhost} style={{ background: GESTRICHELT_HELLBLAU }} />
              <Seg seg={status.overrun} style={{ background: GESTRICHELT_ROT }} />
            </Row>

            <Row
              label="Ist-Kosten kum."
              value={
                <span
                  data-testid="ist-wert"
                  className={status.istOverPlan ? "text-rose-700 font-semibold" : "text-gray-700"}
                >
                  {status.istOverPlan ? "⚠ " : ""}
                  {chf(ist)}
                </span>
              }
            >
              <div
                className="absolute top-0 h-full rounded-sm"
                style={{ width: `${status.istPct}%`, backgroundColor: "var(--forge-red)" }}
              />
              <div
                className="absolute top-[-3px] bottom-[-3px] w-px"
                style={{ left: `${status.planPct}%`, backgroundColor: "var(--forge-blue)" }}
              />
            </Row>

            <Row
              label="AK verrechnet"
              value={
                <span className={ak === 0 ? "text-gray-400" : "text-gray-700"}>
                  {chf(ak)}
                  {status.akCapped && (
                    <span className="ml-1 text-[10px] text-gray-500">gedeckelt</span>
                  )}
                </span>
              }
            >
              <div
                className="absolute top-0 h-full rounded-sm"
                style={{ width: `${status.akPct}%`, backgroundColor: "var(--forge-green)" }}
              />
              <div
                className="absolute top-[-3px] bottom-[-3px] w-px"
                style={{ left: `${status.planPct}%`, backgroundColor: "var(--forge-blue)" }}
              />
            </Row>
          </div>

          <div className="border-l-2 border-gray-200 pl-4">
            <div className="text-[10px] uppercase tracking-wider font-semibold text-gray-500">
              Offen (Plan-WV − AK)
            </div>
            <div className="text-xl font-semibold text-gray-900 tabular-nums">
              {chf(status.offen)}
            </div>
            <div className="text-[12px] text-gray-500 tabular-nums">
              {status.offenPct.toFixed(1)} % von Plan-WV
            </div>
            {status.istOverPlan && (
              <div className="mt-1 text-[11px] text-rose-700 tabular-nums">
                Ist über Plan-WV: +{chf(status.istOverPlanAbs)} (+
                {status.istOverPlanPct.toFixed(1)} %)
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [x] **Step 4: Test laufen lassen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run ProjektStatusChart`
Expected: PASS (4 Tests)

- [x] **Step 5: In die Detailseite einbauen und Überschriften anpassen**

In `frontend/src/pages/ProjektDetailPage.tsx`:

1. Import ergänzen:

```tsx
import ProjektStatusChart from "../components/ProjektStatusChart";
```

2. Überschrift der bestehenden Visualisierungskarte (aktuell Zeile 198)
   umbenennen:

```tsx
        <h2 className="text-[15px] font-semibold text-gray-900">Projektkategorien auf einen Blick</h2>
```

3. Tabellen-Spaltenkopf (aktuell Zeile 636) „Soll-Offerte" → „Offerte":

```tsx
                      <span className="inline-flex items-center justify-end gap-1"><Pencil size={11} className="text-gray-400" />Offerte</span>
```

4. Chart einsetzen — zwischen Kostenpositionen-Karte und
   `<ProjectVisualization>` (aktuell Zeile 861):

```tsx
          {/* Projektstatus (Plan-WV / Ist / AK verrechnet) */}
          {showPositionen && (
            <ProjektStatusChart
              planWV={wvSummeNum}
              sollWV={wvSummeNum}
              ist={summeIstKosten}
              ak={0}
            />
          )}

          {/* Visualisierung */}
          {showPositionen && <ProjectVisualization rows={vizRows} />}
```

`wvSummeNum` und `summeIstKosten` sind an dieser Stelle bereits definiert
(Zeilen 392 und 402). Plan-WV = Soll-WV = `wvSumme`, AK = 0, bis das Backend
eigene Werte liefert.

- [x] **Step 6: Seitentest ergänzen**

In `frontend/src/pages/ProjektDetailPage.test.tsx`. Der vorhandene Helfer
heisst `renderPage(capabilities)` (Zeile 115) und nimmt
`{ canUpdate, canDelete }`. Zwei neue Tests ans Ende der Datei:

```tsx
describe("ProjektDetailPage – Visualisierungskarten", () => {
  it("zeigt beide Karten mit ihren Titeln", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    expect(
      await screen.findByText("Projektstatus auf einen Blick"),
    ).toBeInTheDocument();
    expect(screen.getByText("Projektkategorien auf einen Blick")).toBeInTheDocument();
  });

  it("nennt die erste Wertspalte Offerte", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    expect(await screen.findByText("Offerte")).toBeInTheDocument();
    expect(screen.queryByText("Soll-Offerte")).not.toBeInTheDocument();
  });
});
```

Und den bestehenden Test bei Zeile ~162 erweitern — er prüft bisher nur den
alten Kartentitel, der jetzt der neuen Karte gehört:

```tsx
    expect(
      screen.queryByText("Projektstatus auf einen Blick"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Projektkategorien auf einen Blick"),
    ).not.toBeInTheDocument();
```

`await screen.findByText("Offerte")` ist eindeutig: „Offerte exkl. MwSt."
ist ein anderer, vollständiger Textknoten, und `findByText` matcht exakt.

- [x] **Step 7: Frontend-Tests laufen lassen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run`
Expected: PASS (alle Dateien)

- [x] **Step 8: Commit**

```bash
git add frontend/src/components/ProjektStatusChart.tsx \
        frontend/src/components/ProjektStatusChart.test.tsx \
        frontend/src/pages/ProjektDetailPage.tsx \
        frontend/src/pages/ProjektDetailPage.test.tsx \
        docs/superpowers/plans/2026-09-13-projektstatus-chart-rechnungen.md
git commit -m "feat(frontend): Chart Projektstatus auf einen Blick

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Wn4HSteRch4Z7TwLgvAoQ3"
```

---

## Task 5: Frontend — Spalte „Projektstatus" in der Projektliste

**Files:**
- Create: `frontend/src/components/ProjektStatusMini.tsx`
- Test: `frontend/src/components/ProjektStatusMini.test.tsx` (neu)
- Modify: `frontend/src/pages/ProjektListePage.tsx` (Zeilen 9, 91-123, 373, 376, 420)
- Modify: `frontend/src/pages/ProjektListePage.test.tsx` (Zeile 439-440)

**Interfaces:**
- Consumes: `getProjektStatus` aus Task 3.
- Produces: `<ProjektStatusMini planWV sollWV ist ak />` (Default-Export).

- [x] **Step 1: Failing Test schreiben**

`frontend/src/components/ProjektStatusMini.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ProjektStatusMini from "./ProjektStatusMini";

afterEach(cleanup);

describe("ProjektStatusMini", () => {
  it("zeigt offenen Betrag und Prozent", () => {
    render(<ProjektStatusMini planWV={250000} sollWV={250000} ist={168400} ak={120000} />);
    expect(screen.getByTestId("mini-text")).toHaveTextContent("130'000 offen · 52 %");
  });

  it("faerbt den ganzen Text rot und haengt ein Warnzeichen an, wenn Ist ueber Plan-WV liegt", () => {
    render(<ProjektStatusMini planWV={250000} sollWV={250000} ist={290000} ak={120000} />);
    const text = screen.getByTestId("mini-text");
    expect(text).toHaveTextContent("130'000 offen · 52 % ⚠");
    expect(text.className).toContain("text-rose-700");
  });

  it("zeigt einen Hinweis ohne Plan-WV", () => {
    render(<ProjektStatusMini planWV={null} sollWV={null} ist={0} ak={0} />);
    expect(screen.getByText("keine WV-Summe")).toBeInTheDocument();
  });
});
```

- [x] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run ProjektStatusMini`
Expected: FAIL — `Failed to resolve import "./ProjektStatusMini"`

- [x] **Step 3: Implementieren**

`frontend/src/components/ProjektStatusMini.tsx`:

```tsx
import { chf } from "../utils/format";
import { getProjektStatus } from "../utils/projektStatus";

type Props = {
  planWV: number | null;
  sollWV: number | null;
  ist: number;
  ak: number;
};

export default function ProjektStatusMini({ planWV, sollWV, ist, ak }: Props) {
  const status = getProjektStatus({ planWV, sollWV, ist, ak });
  if (!status) {
    return <span className="text-[12px] italic text-gray-400">keine WV-Summe</span>;
  }

  // Der Mini-Balken skaliert immer auf Plan-WV; ein Ist darüber sitzt am Rand.
  const akBreite = (status.akPct / status.planPct) * 100;
  const istPosition = Math.min((status.istPct / status.planPct) * 100, 100);

  return (
    <div className="flex items-center gap-2.5">
      <span className="relative w-[110px] h-1.5 rounded-full shrink-0 bg-gray-100">
        <span
          className="absolute inset-0 rounded-full"
          style={{ backgroundColor: "var(--forge-blue-light)" }}
        />
        <span
          className="absolute top-0 bottom-0 left-0 rounded-full"
          style={{ width: `${akBreite}%`, backgroundColor: "var(--forge-green)" }}
        />
        <span
          className="absolute top-[-2px] bottom-[-2px]"
          style={{
            left: `calc(${istPosition}% - ${status.istOverPlan ? "4px" : "1px"})`,
            width: status.istOverPlan ? "4px" : "2px",
            backgroundColor: "var(--forge-red)",
          }}
        />
      </span>
      <span
        data-testid="mini-text"
        className={`text-[12px] tabular-nums whitespace-nowrap ${
          status.istOverPlan ? "text-rose-700 font-medium" : "text-gray-600"
        }`}
      >
        <span className="font-medium text-inherit">
          {chf(status.offen, { withCurrency: false }).replace(".00", "")}
        </span>{" "}
        offen · {status.offenPct.toFixed(0)} %{status.istOverPlan ? " ⚠" : ""}
      </span>
    </div>
  );
}
```

- [x] **Step 4: Test laufen lassen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run ProjektStatusMini`
Expected: PASS (3 Tests)

- [x] **Step 5: Liste umbauen**

In `frontend/src/pages/ProjektListePage.tsx`:

1. Import tauschen (Zeile 9) — `getDeviation`/`DEV_STYLES` werden hier nicht
   mehr gebraucht:

```tsx
import ProjektStatusMini from "../components/ProjektStatusMini";
```

2. Die Funktion `DeviationCell` (Zeilen 91-123) **ersatzlos löschen**.
   `utils/deviation.ts` bleibt bestehen — die Detailseite nutzt es weiter.

3. Spaltenkopf „WV + Zusätze" (Zeile 373) → „Plan-WV" (der Wert bleibt
   `summeWvPlus`):

```tsx
                        Plan-WV
```

4. Spaltenkopf „Abweichung zu Ist" (Zeile 376) → „Projektstatus":

```tsx
                        Projektstatus
```

5. Zelle (Zeile 419-421) ersetzen:

```tsx
                        <td className="px-4 py-3">
                          <ProjektStatusMini
                            planWV={p.projektKennzahlenList.items[0]?.summeWvPlus?.value ?? null}
                            sollWV={p.projektKennzahlenList.items[0]?.summeWvPlus?.value ?? null}
                            ist={p.projektKennzahlenList.items[0]?.summeIstKosten?.value ?? 0}
                            ak={0}
                          />
                        </td>
```

- [x] **Step 6: Listentest anpassen**

In `frontend/src/pages/ProjektListePage.test.tsx` die beiden Zeilen 439-440
(Monteur sieht keine Finanzspalten) auf die neuen Titel umstellen und einen
Test für die neue Spalte ergänzen:

```tsx
    expect(screen.queryByText("Plan-WV")).not.toBeInTheDocument();
    expect(screen.queryByText("Projektstatus")).not.toBeInTheDocument();
```

Der Helfer in dieser Datei heisst `renderPage()` (Zeile 104, ohne Argumente):

```tsx
  it("zeigt die Projektstatus-Spalte mit offenem Betrag", async () => {
    renderPage();
    expect(await screen.findByText("Projektstatus")).toBeInTheDocument();
    expect(screen.getAllByTestId("mini-text")[0]).toHaveTextContent("offen");
  });
```

Der Standard-Mock (`projekt()`, Zeile 49) liefert `summeWvPlus` 9'500 und
`summeIstKosten` 8'000 — also Plan-WV 9'500, AK 0, Offen 9'500 (100 %).

- [x] **Step 7: Frontend-Tests laufen lassen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run`
Expected: PASS

- [x] **Step 8: Commit**

```bash
git add frontend/src/components/ProjektStatusMini.tsx \
        frontend/src/components/ProjektStatusMini.test.tsx \
        frontend/src/pages/ProjektListePage.tsx \
        frontend/src/pages/ProjektListePage.test.tsx \
        docs/superpowers/plans/2026-09-13-projektstatus-chart-rechnungen.md
git commit -m "feat(frontend): Projektstatus-Spalte in der Projektliste

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Wn4HSteRch4Z7TwLgvAoQ3"
```

---

## Task 6: Frontend — Rechnungen-Pop-up

**Files:**
- Create: `frontend/src/components/RechnungenModal.tsx`
- Test: `frontend/src/components/RechnungenModal.test.tsx` (neu)
- Modify: `frontend/src/utils/format.ts` (Funktion `deDate`)
- Modify: `frontend/src/graphql/queries.ts` (`GET_PROJEKT_RECHNUNGEN`)
- Modify: `src/forge/graphql_metric_operations.py` (Allowlist)
- Modify: `frontend/src/pages/ProjektDetailPage.tsx` (Ist-Zellen klickbar)
- Modify: `frontend/src/pages/ProjektDetailPage.test.tsx`

**Interfaces:**
- Consumes: Backend-Felder aus Task 1 und 2.
- Produces: `type RechnungRow`, `<RechnungenModal title rows loading error onClose />`
  (Default-Export); `deDate(iso: string | null): string`.

- [x] **Step 1: Failing Tests schreiben**

`frontend/src/components/RechnungenModal.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RechnungenModal, { type RechnungRow } from "./RechnungenModal";

afterEach(cleanup);

const rows: RechnungRow[] = [
  {
    id: "1",
    dokumentNr: "LR-100",
    rechnungsdatum: "2024-03-01",
    firmenname: "Beta AG",
    zeilenTitel: "Ventilator",
    buchungskonto: { accountNo: "4001", name: "Apparate" },
    status: "paid",
    faelligkeitsdatum: "2024-03-31",
    ueberfaellig: false,
    betrag: 1077,
    steuerBerechnet: 77,
    nettoBetrag: 1000,
  },
  {
    id: "2",
    dokumentNr: "LR-050",
    rechnungsdatum: "2024-01-15",
    firmenname: "Alpha GmbH",
    zeilenTitel: null,
    buchungskonto: null,
    status: "open",
    faelligkeitsdatum: "2024-02-15",
    ueberfaellig: true,
    betrag: 500,
    steuerBerechnet: 0,
    nettoBetrag: 500,
  },
];

function zeilenTexte(): string[] {
  const body = screen.getByTestId("rechnungen-body");
  return within(body)
    .getAllByRole("row")
    .map((row) => row.querySelectorAll("td")[1]?.textContent ?? "");
}

describe("RechnungenModal", () => {
  it("zeigt Titel, Zeilen und Fusszeile", () => {
    render(<RechnungenModal title="Rechnungen · Apparate" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    expect(screen.getByText("Rechnungen · Apparate")).toBeInTheDocument();
    expect(screen.getByText("LR-100")).toBeInTheDocument();
    expect(screen.getByText("4001 Apparate")).toBeInTheDocument();
    expect(screen.getByText("2 Rechnungen · Netto CHF 1'500.00")).toBeInTheDocument();
  });

  it("sortiert nach Datum absteigend als Standard", () => {
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    expect(zeilenTexte()).toEqual(["LR-100", "LR-050"]);
  });

  it("dreht die Sortierung beim Klick auf den Spaltenkopf", () => {
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Datum/ }));
    expect(zeilenTexte()).toEqual(["LR-050", "LR-100"]);
  });

  it("sortiert nach Lieferant aufsteigend", () => {
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Lieferant/ }));
    expect(zeilenTexte()).toEqual(["LR-050", "LR-100"]);
  });

  it("markiert überfällige Rechnungen", () => {
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={vi.fn()} />);
    expect(screen.getByTestId("faellig-2")).toHaveTextContent("⚠");
  });

  it("schliesst per Button und per Escape", () => {
    const onClose = vi.fn();
    render(<RechnungenModal title="T" rows={rows} loading={false} error={null} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Schliessen" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("zeigt Lade- und Leerzustand", () => {
    const { rerender } = render(
      <RechnungenModal title="T" rows={[]} loading error={null} onClose={vi.fn()} />,
    );
    expect(screen.getByText("Lade Rechnungen…")).toBeInTheDocument();
    rerender(<RechnungenModal title="T" rows={[]} loading={false} error={null} onClose={vi.fn()} />);
    expect(screen.getByText("Keine Rechnungen")).toBeInTheDocument();
  });
});
```

- [x] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run RechnungenModal`
Expected: FAIL — `Failed to resolve import "./RechnungenModal"`

- [x] **Step 3: `deDate` ergänzen**

Ans Ende von `frontend/src/utils/format.ts`:

```ts
/** ISO-Datum (2024-03-01) als 01.03.2024; leer bleibt leer. */
export function deDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [jahr, monat, tag] = iso.slice(0, 10).split("-");
  if (!jahr || !monat || !tag) return "–";
  return `${tag}.${monat}.${jahr}`;
}
```

- [x] **Step 4: Modal implementieren**

`frontend/src/components/RechnungenModal.tsx`:

```tsx
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { chf, deDate } from "../utils/format";

export type RechnungRow = {
  id: string;
  dokumentNr: string;
  rechnungsdatum: string;
  firmenname: string;
  zeilenTitel: string | null;
  buchungskonto: { accountNo: string; name: string } | null;
  status: string;
  faelligkeitsdatum: string | null;
  ueberfaellig: boolean;
  betrag: number;
  steuerBerechnet: number;
  nettoBetrag: number;
};

type SortKey =
  | "rechnungsdatum"
  | "dokumentNr"
  | "firmenname"
  | "zeilenTitel"
  | "buchungskonto"
  | "status"
  | "faelligkeitsdatum"
  | "betrag"
  | "steuerBerechnet"
  | "nettoBetrag";

type Spalte = {
  key: SortKey;
  label: string;
  numerisch: boolean;
  rechts: boolean;
};

const SPALTEN: Spalte[] = [
  { key: "rechnungsdatum", label: "Datum", numerisch: false, rechts: false },
  { key: "dokumentNr", label: "Dokument-Nr", numerisch: false, rechts: false },
  { key: "firmenname", label: "Lieferant", numerisch: false, rechts: false },
  { key: "zeilenTitel", label: "Zeilentitel", numerisch: false, rechts: false },
  { key: "buchungskonto", label: "Buchungskonto", numerisch: false, rechts: false },
  { key: "status", label: "Status", numerisch: false, rechts: false },
  { key: "faelligkeitsdatum", label: "Fällig am", numerisch: false, rechts: false },
  { key: "betrag", label: "Brutto", numerisch: true, rechts: true },
  { key: "steuerBerechnet", label: "Steuer", numerisch: true, rechts: true },
  { key: "nettoBetrag", label: "Netto", numerisch: true, rechts: true },
];

function sortWert(row: RechnungRow, key: SortKey): string | number {
  if (key === "buchungskonto") return row.buchungskonto?.accountNo ?? "";
  const wert = row[key];
  if (wert == null) return "";
  return typeof wert === "number" ? wert : String(wert);
}

export default function RechnungenModal({
  title,
  rows,
  loading,
  error,
  onClose,
}: {
  title: string;
  rows: RechnungRow[];
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("rechnungsdatum");
  const [absteigend, setAbsteigend] = useState(true);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function sortiereNach(spalte: Spalte) {
    if (spalte.key === sortKey) {
      setAbsteigend((a) => !a);
      return;
    }
    setSortKey(spalte.key);
    // Zahlen und Daten interessieren meist absteigend, Text aufsteigend.
    setAbsteigend(spalte.numerisch || spalte.key.includes("datum"));
  }

  const sortiert = [...rows].sort((a, b) => {
    const va = sortWert(a, sortKey);
    const vb = sortWert(b, sortKey);
    const cmp =
      typeof va === "number" && typeof vb === "number"
        ? va - vb
        : String(va).localeCompare(String(vb), "de");
    return absteigend ? -cmp : cmp;
  });

  const nettoSumme = rows.reduce((summe, r) => summe + r.nettoBetrag, 0);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="bg-white rounded-lg shadow-xl w-full max-w-[1100px] mt-10"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-[15px] font-semibold text-gray-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schliessen"
            className="p-1 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {loading ? (
          <p className="px-6 py-8 text-sm text-gray-500">Lade Rechnungen…</p>
        ) : error ? (
          <p
            className="m-6 rounded-lg p-4 border text-sm"
            style={{
              color: "var(--forge-red)",
              borderColor: "var(--forge-red)",
              backgroundColor: "var(--forge-red-soft)",
            }}
          >
            {error}
          </p>
        ) : rows.length === 0 ? (
          <p className="px-6 py-8 text-sm text-gray-500">Keine Rechnungen</p>
        ) : (
          <>
            <div className="overflow-x-auto max-h-[70vh]">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b border-gray-200">
                    {SPALTEN.map((spalte) => (
                      <th
                        key={spalte.key}
                        className={`px-3 py-2.5 text-[11px] uppercase tracking-wider font-semibold text-gray-500 ${
                          spalte.rechts ? "text-right" : "text-left"
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => sortiereNach(spalte)}
                          className="inline-flex items-center gap-1 hover:text-gray-900 transition-colors"
                        >
                          {spalte.label}
                          <span className="text-[9px]">
                            {sortKey === spalte.key ? (absteigend ? "▼" : "▲") : ""}
                          </span>
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody data-testid="rechnungen-body">
                  {sortiert.map((row) => (
                    <tr key={row.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/50">
                      <td className="px-3 py-2 text-gray-700 tabular-nums whitespace-nowrap">
                        {deDate(row.rechnungsdatum)}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-600">{row.dokumentNr}</td>
                      <td className="px-3 py-2 text-gray-800">{row.firmenname}</td>
                      <td className="px-3 py-2 text-gray-600">{row.zeilenTitel ?? "–"}</td>
                      <td className="px-3 py-2 text-gray-600 whitespace-nowrap">
                        {row.buchungskonto
                          ? `${row.buchungskonto.accountNo} ${row.buchungskonto.name}`
                          : "–"}
                      </td>
                      <td className="px-3 py-2 text-gray-600">{row.status}</td>
                      <td
                        data-testid={`faellig-${row.id}`}
                        className={`px-3 py-2 tabular-nums whitespace-nowrap ${
                          row.ueberfaellig ? "text-rose-700 font-medium" : "text-gray-600"
                        }`}
                      >
                        {row.ueberfaellig ? "⚠ " : ""}
                        {deDate(row.faelligkeitsdatum)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600">
                        {chf(row.betrag, { withCurrency: false })}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600">
                        {chf(row.steuerBerechnet, { withCurrency: false })}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium text-gray-900">
                        {chf(row.nettoBetrag, { withCurrency: false })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-6 py-3 border-t border-gray-100 text-[12px] text-gray-600 tabular-nums">
              {rows.length} {rows.length === 1 ? "Rechnung" : "Rechnungen"} · Netto{" "}
              {chf(nettoSumme)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

- [x] **Step 5: Tests laufen lassen**

Run: `devcontainer exec --workspace-folder . npm --prefix frontend test -- --run RechnungenModal`
Expected: PASS (7 Tests)

- [x] **Step 6: Query ergänzen**

Ans Ende von `frontend/src/graphql/queries.ts`:

```ts
export const GET_PROJEKT_RECHNUNGEN = gql`
  query ProjektRechnungen($id: ID!) {
    projekt(id: $id) {
      id
      projektKennzahlenList {
        items {
          rechnungen {
            ...RechnungFelder
          }
        }
      }
      istWertList {
        items {
          kostenart {
            schluessel
          }
          rechnungen {
            ...RechnungFelder
          }
        }
      }
    }
  }

  fragment RechnungFelder on LieferantenrechnungType {
    id
    dokumentNr
    rechnungsdatum
    firmenname
    zeilenTitel
    status
    faelligkeitsdatum
    ueberfaellig
    betrag
    steuerBerechnet
    nettoBetrag
    buchungskonto {
      accountNo
      name
    }
  }
`;
```

Und in `src/forge/graphql_metric_operations.py` den Eintrag `"ProjektRechnungen"`
in die Allowlist aufnehmen (alphabetisch zwischen `"ProjektListeUpdated"` und
`"ProjektUpdated"`).

- [x] **Step 7: Detailseite verdrahten**

In `frontend/src/pages/ProjektDetailPage.tsx`:

1. Imports:

```tsx
import { useLazyQuery, useMutation, useQuery, useSubscription } from "@apollo/client/react";
import RechnungenModal, { type RechnungRow } from "../components/RechnungenModal";
import { GET_PROJEKT_RECHNUNGEN } from "../graphql/queries";
```

2. Typen bei den anderen Query-Typen ergänzen:

```tsx
type RechnungenData = {
  projekt: {
    projektKennzahlenList: { items: { rechnungen: RechnungRow[] | null }[] };
    istWertList: { items: { kostenart: { schluessel: string }; rechnungen: RechnungRow[] | null }[] };
  } | null;
};
```

3. State und Lazy-Query in der Komponente (nach den bestehenden `useState`):

```tsx
  const [rechnungenModal, setRechnungenModal] = useState<
    { title: string; schluessel: string | null } | null
  >(null);
  const [ladeRechnungen, rechnungenQuery] = useLazyQuery<RechnungenData>(
    GET_PROJEKT_RECHNUNGEN,
    { variables: { id } },
  );

  function oeffneRechnungen(schluessel: string | null, title: string) {
    void ladeRechnungen();
    setRechnungenModal({ title, schluessel });
  }

  const modalRows: RechnungRow[] = (() => {
    const projekt = rechnungenQuery.data?.projekt;
    if (!rechnungenModal || !projekt) return [];
    if (rechnungenModal.schluessel === null) {
      return projekt.projektKennzahlenList.items[0]?.rechnungen ?? [];
    }
    return (
      projekt.istWertList.items.find(
        (item) => item.kostenart.schluessel === rechnungenModal.schluessel,
      )?.rechnungen ?? []
    );
  })();
```

4. Ist-Zelle in der Tabelle klickbar machen — den bestehenden Block
   (aktuell Zeilen 760-765) ersetzen:

```tsx
                        {/* Ist — heatmap color, klickbar wenn ein Wert da ist */}
                        <td className={istCls} style={pairDiv}>
                          {istWert?.istKostenWert != null ? (
                            <button
                              type="button"
                              onClick={() =>
                                oeffneRechnungen(
                                  schluessel,
                                  `Rechnungen · ${ART_LABELS[schluessel] ?? schluessel}`,
                                )
                              }
                              className="inline-flex items-center gap-1 underline decoration-dotted underline-offset-2 hover:decoration-solid cursor-pointer"
                            >
                              {(devLevel === "over" || devLevel === "warn") && (
                                <span className="text-[10px]">⚠</span>
                              )}
                              {istDisplay}
                            </button>
                          ) : (
                            istDisplay
                          )}
                        </td>
```

5. Ist-Zelle der Summenzeile (aktuell Zeile 785) ersetzen:

```tsx
                        {footerErp(
                          summeIstKosten > 0 ? (
                            <button
                              type="button"
                              onClick={() => oeffneRechnungen(null, `Alle Rechnungen · ${p.name}`)}
                              className="font-semibold underline decoration-dotted underline-offset-2 hover:decoration-solid cursor-pointer"
                            >
                              {chf(summeIstKosten)}
                            </button>
                          ) : (
                            <span className="font-semibold">{chf(summeIstKosten || null)}</span>
                          ),
                          pairDiv,
                        )}
```

6. Modal rendern — direkt vor dem schliessenden `</Layout>`:

```tsx
      {rechnungenModal && (
        <RechnungenModal
          title={rechnungenModal.title}
          rows={modalRows}
          loading={rechnungenQuery.loading}
          error={rechnungenQuery.error ? rechnungenQuery.error.message : null}
          onClose={() => setRechnungenModal(null)}
        />
      )}
```

- [x] **Step 8: Seitentest ergänzen**

In `frontend/src/pages/ProjektDetailPage.test.tsx` einen Mock für die neue
Query ergänzen, ihn in die Mock-Liste von `renderPage` (Zeile 119)
aufnehmen und einen Test schreiben. Der Mock braucht dieselben Variablen
(`{ id: "1" }`):

```tsx
const rechnungenMock = {
  request: { query: GET_PROJEKT_RECHNUNGEN, variables: { id: "1" } },
  result: {
    data: {
      projekt: {
        id: "1",
        projektKennzahlenList: { items: [{ rechnungen: [] }] },
        istWertList: {
          items: [
            {
              kostenart: { schluessel: "apparate" },
              rechnungen: [
                {
                  id: "7",
                  dokumentNr: "LR-777",
                  rechnungsdatum: "2024-05-02",
                  firmenname: "Muster AG",
                  zeilenTitel: "Lüfter",
                  status: "paid",
                  faelligkeitsdatum: "2024-06-01",
                  ueberfaellig: false,
                  betrag: 1077,
                  steuerBerechnet: 77,
                  nettoBetrag: 1000,
                  buchungskonto: { accountNo: "4001", name: "Apparate" },
                },
              ],
            },
          ],
        },
      },
    },
  },
};
```

Die Mock-Liste in `renderPage` (Zeile 119) um `rechnungenMock` erweitern:

```tsx
        mocks={[projektMock(capabilities), kostenartMock, statusMock, subscriptionMock, projektleiterMock, rechnungenMock]}
```

Der bestehende `projektMock` enthält bereits einen `istWertList`-Eintrag für
`apparate` mit `istKostenWert: { value: 400, unit: "CHF" }` (Zeile 82-88) —
die Ist-Zelle zeigt also „CHF 400.00":

```tsx
  it("öffnet das Rechnungen-Pop-up beim Klick auf einen Ist-Wert", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    const istZelle = await screen.findByRole("button", { name: /400\.00/ });
    fireEvent.click(istZelle);
    expect(await screen.findByText("LR-777")).toBeInTheDocument();
    expect(screen.getByText("Rechnungen · Apparate")).toBeInTheDocument();
  });

  it("öffnet alle Rechnungen über die Summenzeile", async () => {
    renderPage({ canUpdate: false, canDelete: false });
    const summe = await screen.findByRole("button", { name: /950\.00/ });
    fireEvent.click(summe);
    expect(await screen.findByText("Alle Rechnungen · Testprojekt")).toBeInTheDocument();
  });
```

**Vorher zwingend:** Im `projektMock` stehen `summeIstKosten` (Zeile 58) und
der Apparate-`istKostenWert` (Zeile 86) beide auf 400 — beide Zellen zeigen
dann „CHF 400.00" und `findByRole` findet zwei Treffer („found multiple
elements"). Deshalb im Mock die Summe von der Kategorie trennen; keine
bestehende Assertion hängt an diesen Zahlen:

```tsx
                summeIstKosten: { value: 950, unit: "CHF" },
```

```tsx
                bisherVerrechnet: { value: -950, unit: "CHF" },
```

Der Selektor der Summenzeile lautet dann `{ name: /950\.00/ }`.

`fireEvent` aus `@testing-library/react` importieren, falls die Datei es noch
nicht tut.

- [x] **Step 9: Volles Gate**

Run: `devcontainer exec --workspace-folder . uv run pre-commit run --all-files`
Expected: ruff, pytest, mypy, vitest alle **Passed**

- [x] **Step 10: Commit**

```bash
git add frontend/src/components/RechnungenModal.tsx \
        frontend/src/components/RechnungenModal.test.tsx \
        frontend/src/utils/format.ts \
        frontend/src/graphql/queries.ts \
        frontend/src/pages/ProjektDetailPage.tsx \
        frontend/src/pages/ProjektDetailPage.test.tsx \
        src/forge/graphql_metric_operations.py \
        docs/superpowers/plans/2026-09-13-projektstatus-chart-rechnungen.md
git commit -m "feat(frontend): Rechnungen-Pop-up hinter den Ist-Werten

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Wn4HSteRch4Z7TwLgvAoQ3"
```

---

## Task 7: Dokumentation nachziehen

**Files:**
- Modify: `docs/specs/designs/projektdetail.md`
- Modify: `docs/specs/projekt.md`

**Interfaces:**
- Consumes: alles Vorherige.
- Produces: —

- [x] **Step 1: Detailseiten-Doku ergänzen**

In `docs/specs/designs/projektdetail.md` einen Abschnitt zum Chart aufnehmen:
Reihenfolge der Karten (Kostenpositionen → Projektstatus → Projektkategorien),
die vier Kennzahlen mit ihren heutigen Quellen (Plan-WV = Soll-WV =
`wvSumme`, AK verrechnet = 0), die Sonderfälle (Ist > Plan-WV, AK gedeckelt,
keine WV-Summe) und die Klickregel für die Ist-Zellen („klickbar, wenn ein
Wert angezeigt wird").

- [x] **Step 2: Listen-Doku ergänzen**

In `docs/specs/projekt.md` den Listen-Mockup (ab Zeile 215) auf die neuen
Spalten umstellen: `Offerte · Plan-WV · Projektstatus · Phase`.

- [x] **Step 3: Volles Gate**

Run: `devcontainer exec --workspace-folder . uv run pre-commit run --all-files`
Expected: alle Hooks **Passed**

- [x] **Step 4: Commit**

```bash
git add docs/specs/designs/projektdetail.md docs/specs/projekt.md \
        docs/superpowers/plans/2026-09-13-projektstatus-chart-rechnungen.md
git commit -m "docs: Projektstatus-Chart und Rechnungen-Pop-up dokumentiert

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Wn4HSteRch4Z7TwLgvAoQ3"
```

---

## Offene Punkte für später (nicht in diesem Plan)

- Gemeinkosten-Ist (eigener Branch, vom Nutzer angekündigt).
- „AK verrechnet" aus dem Backend statt konstant 0.
- Plan-WV als eigener Wert statt gleich WV-Summe.
- Rechnungen auf Konto 44401 (Transport und Montage) zählen in
  `summeIstKosten`, aber in keiner Kategorie — sie erscheinen nur im
  „Alle Rechnungen"-Pop-up. Bestehendes Verhalten (TODO stunden.md),
  hier bewusst nicht angefasst.
