# ADR 004 – Teststrategie: pytest + django.test.TestCase

**Datum:** 2026-03-19
**Status:** Akzeptiert

## Kontext

Das Projekt nutzt pytest als Test-Runner (via `pre-commit` und CI). Für Tests die
Datenbankzustand aufbauen — insbesondere GeneralManager Field Rules, Permission-Checks
und CRUD-Integrationstests — entstehen mit reinem pytest Probleme:

- Django-`TransactionTestCase` und ORM-Transaktionen müssen manuell verwaltet werden
- Kein automatisches Rollback zwischen Tests → Datenlecks möglich
- `setUp`/`tearDown` fehlen als klarer Lebenszyklusmechanismus

## Entscheidung

Wir kombinieren beide Werkzeuge nach Testtyp:

| Testtyp | Werkzeug |
|---------|----------|
| Datenbankzugriff (Rules, Permissions, CRUD, Integration) | `django.test.TestCase` |
| Reine Logik ohne DB | pytest-Funktion |

pytest bleibt der **Runner** für beides. Die Wahl betrifft nur den Teststil.

## Begründung

- `django.test.TestCase` wraps jeden Test in einer Transaktion → automatisches Rollback,
  kein Datenleck zwischen Tests
- `setUp`/`tearDown` geben einen klaren Ort für Testdaten-Aufbau
- Für Field Rules und Permissions ist ein echter DB-Roundtrip nötig — Mocks würden
  die Validierungslogik von GeneralManager umgehen
- pytest-Funktionen bleiben für datenbankfreie Logik: schlanker, schneller, kein Overhead

## Konsequenzen

- Tests mit DB-Zugriff erben von `django.test.TestCase`
- Testdaten werden über **Factories** erstellt (kein fixtures-YAML)
- Pre-commit und CI laufen weiterhin via `uv run pytest` — beide Stile werden erkannt
- Dokumentation: `docs/skills/testing/SKILL.md`

## Verworfene Alternativen

- **Nur pytest mit `@pytest.mark.django_db`**: Kein automatisches Rollback,
  kein `setUp`/`tearDown`-Pattern, Datenlecks bei komplexen Testszenarien
- **Nur `django.test.TestCase`**: Pytest-Fixtures und parametrize nicht nutzbar
  für reine Logiktests — unnötig schwerfällig
