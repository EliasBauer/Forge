# Backend-Testing

> Wann welches Test-Werkzeug einsetzen — und warum.
> Entscheidungshintergrund: [ADR 004](../../adr/004-teststrategie-pytest-vs-django-testcase.md)

---

## Faustregeln

| Situation                            | Werkzeug               |
| ------------------------------------ | ---------------------- |
| Test braucht Datenbank               | `django.test.TestCase` |
| Model-Validierung / Field Rules      | `django.test.TestCase` |
| Permissions / Gruppen                | `django.test.TestCase` |
| GeneralManager CRUD                  | `django.test.TestCase` |
| Integrationstest (mehrere Models)    | `django.test.TestCase` |
| Reine Logik / Berechnungen (kein DB) | pytest-Funktion        |
| Utility-Funktionen                   | pytest-Funktion        |

---

## `django.test.TestCase`

Verwenden wann immer **Datenbankzustand aufgebaut** werden muss.

Django wraps jeden Test automatisch in eine Transaktion die am Ende zurückgerollt
wird — kein manuelles Cleanup nötig.

```python
from django.test import TestCase
from django.contrib.auth.models import User
from apps.projekt.models import Projekt
from general_manager.measurement import Measurement


class ProjektValidierungTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="x")
        self.projekt = Projekt.create(
            creator_id=self.user.id,
            name="Test",
            auftragsnummer="T-001",
            offerte_summe=Measurement(10000, "CHF"),
            wv_summe=Measurement(9000, "CHF"),
        )

    def test_auftragsnummer_eindeutig(self):
        with self.assertRaises(Exception):
            Projekt.create(
                creator_id=self.user.id,
                name="Duplikat",
                auftragsnummer="T-001",
                offerte_summe=Measurement(5000, "CHF"),
                wv_summe=Measurement(4000, "CHF"),
            )

    def test_offerte_summe_positiv(self):
        # Rule-Validierung prüfen
        ...
```

### Permissions testen

```python
class ProjektPermissionTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Group
        self.admin = User.objects.create_user("admin", password="x", is_staff=True)
        self.monteur = User.objects.create_user("monteur", password="x")
        gruppe = Group.objects.get(name="Monteur")
        self.monteur.groups.add(gruppe)

    def test_monteur_darf_nicht_erstellen(self):
        from general_manager.permission.base_permission import PermissionCheckError
        with self.assertRaises(PermissionCheckError):
            Projekt.create(creator_id=self.monteur.id, ...)
```

---

## Reines pytest

Für Tests **ohne Datenbankzugriff** — schlanker, schneller, kein Django-Setup nötig.

```python
from decimal import Decimal
from apps.projekt.models import _normalize_decimal_fields


def test_normalize_decimal_fields():
    class Fake:
        val = 6666.02

    _normalize_decimal_fields(Fake(), "val")
    assert Fake.val == Decimal("6666.02")
```

---

## Factories statt Fixtures

Für Testdaten **Factories** verwenden (→ `docs/general_manager-patterns.md` §7),
keine fixtures-YAML-Dateien.

```python
# tests/factories.py
from general_manager.factory import AutoFactory
import factory
from apps.projekt.models import Projekt
from general_manager.measurement import Measurement


class ProjektFactory(AutoFactory):
    interface = Projekt.Interface

    class Meta:
        model = Projekt.Interface._model

    name = factory.Sequence(lambda n: f"Projekt {n}")
    auftragsnummer = factory.Sequence(lambda n: f"2026-{n:03d}")
    offerte_summe = Measurement(10000, "CHF")
    wv_summe = Measurement(9000, "CHF")


# In TestCase:
class MeinTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("t", password="x")
        self.projekt = ProjektFactory.create(creator_id=self.user.id)
```

---

## pytest läuft trotzdem für alles

`pytest` ist der Test-Runner — auch `TestCase`-Klassen werden von pytest
gesammelt und ausgeführt. Die Wahl zwischen `TestCase` und pytest-Funktion
betrifft nur den **Stil**, nicht den Runner.

Pre-commit und CI laufen immer via:

```bash
uv run pytest
```
