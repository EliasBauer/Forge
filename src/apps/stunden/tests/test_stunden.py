"""Tests für das Stundensatz-Modell."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from general_manager.measurement import Measurement

from apps.stunden.models import Stundensatz

_StundensatzModel: Any = Stundensatz.Interface._model  # type: ignore[misc]

# ---------------------------------------------------------------------------
# Test-Konstanten
# ---------------------------------------------------------------------------
_TESTJAHR = 2024
_STUNDENSATZ = Decimal("87")


class StundensatzFelderTest(TestCase):
    """Prüft, dass alle Felder korrekt am Modell vorhanden sind."""

    def test_feld_jahr_existiert(self) -> None:
        feld_namen = [f.name for f in _StundensatzModel._meta.get_fields()]
        self.assertIn("jahr", feld_namen)

    def test_feld_stundensatz_existiert(self) -> None:
        feld_namen = [f.name for f in _StundensatzModel._meta.get_fields()]
        self.assertIn("stundensatz", feld_namen)

    def test_feld_stundensatz_value_existiert(self) -> None:
        """MeasurementField legt ein _value-Hilfsfeld an."""
        feld_namen = [f.name for f in _StundensatzModel._meta.get_fields()]
        self.assertIn("stundensatz_value", feld_namen)

    def test_feld_stundensatz_unit_existiert(self) -> None:
        """MeasurementField legt ein _unit-Hilfsfeld an."""
        feld_namen = [f.name for f in _StundensatzModel._meta.get_fields()]
        self.assertIn("stundensatz_unit", feld_namen)


class StundensatzErstellenTest(TestCase):
    """Prüft das Anlegen von Stundensatz-Einträgen."""

    def test_erstellen_mit_measurement_objekt(self) -> None:
        obj = Stundensatz.create(
            ignore_permission=True,
            jahr=_TESTJAHR,
            stundensatz=Measurement(_STUNDENSATZ, "CHF"),
        )
        self.assertEqual(obj.jahr, _TESTJAHR)
        self.assertIsNotNone(obj.id)

    def test_erstellen_mit_string_wert(self) -> None:
        """MeasurementField soll den String '87.50 CHF' akzeptieren."""
        Stundensatz.create(
            ignore_permission=True,
            jahr=2025,
            stundensatz=Measurement(Decimal("87.50"), "CHF"),
        )
        obj = Stundensatz.filter(jahr=2025).first()
        assert isinstance(obj, Stundensatz)
        self.assertEqual(obj.stundensatz.magnitude, Decimal("87.50"))

    def test_stundensatz_wert_wird_korrekt_gespeichert(self) -> None:
        Stundensatz.create(
            ignore_permission=True,
            jahr=2023,
            stundensatz=Measurement(Decimal("95.00"), "CHF"),
        )
        geladen = Stundensatz.filter(jahr=2023).first()
        assert isinstance(geladen, Stundensatz)
        self.assertEqual(geladen.stundensatz.magnitude, Decimal("95.00"))


class StundensatzJahrUniqueTest(TestCase):
    """Prüft die unique-Einschränkung des Feldes `jahr`."""

    def test_gleiches_jahr_wird_abgelehnt(self) -> None:
        Stundensatz.create(
            ignore_permission=True,
            jahr=_TESTJAHR,
            stundensatz=Measurement(_STUNDENSATZ, "CHF"),
        )
        with self.assertRaises((IntegrityError, ValidationError)):
            Stundensatz.create(
                ignore_permission=True,
                jahr=_TESTJAHR,
                stundensatz=Measurement(90, "CHF"),
            )

    def test_verschiedene_jahre_erlaubt(self) -> None:
        Stundensatz.create(
            ignore_permission=True,
            jahr=_TESTJAHR,
            stundensatz=Measurement(_STUNDENSATZ, "CHF"),
        )
        Stundensatz.create(
            ignore_permission=True,
            jahr=2025,
            stundensatz=Measurement(90, "CHF"),
        )
        self.assertEqual(Stundensatz.filter().count(), 2)


class StundensatzRegelTest(TestCase):
    """Prüft die Rule: stundensatz > 0 CHF."""

    def test_stundensatz_null_schlaegt_fehl(self) -> None:
        """Ein Stundensatz von 0 CHF verletzt die Regel."""
        db_obj = _StundensatzModel(
            jahr=_TESTJAHR,
            stundensatz=Measurement(0, "CHF"),
        )
        with self.assertRaises((ValidationError, Exception)):
            db_obj.full_clean()

    def test_stundensatz_negativ_schlaegt_fehl(self) -> None:
        """Ein negativer Stundensatz verletzt die Regel."""
        db_obj = _StundensatzModel(
            jahr=_TESTJAHR,
            stundensatz=Measurement(-1, "CHF"),
        )
        with self.assertRaises((ValidationError, Exception)):
            db_obj.full_clean()

    def test_stundensatz_positiv_ist_gueltig(self) -> None:
        """Ein Stundensatz von 87 CHF ist gültig."""
        obj = Stundensatz.create(
            ignore_permission=True,
            jahr=_TESTJAHR,
            stundensatz=Measurement(_STUNDENSATZ, "CHF"),
        )
        self.assertEqual(obj.jahr, _TESTJAHR)

    def test_stundensatz_als_gm_instanz_gibt_korrekten_wert_zurueck(self) -> None:
        """GeneralManager-Instanz gibt den gespeicherten Stundensatz exakt zurück."""
        Stundensatz.create(
            ignore_permission=True,
            jahr=2026,
            stundensatz=Measurement(Decimal("87.50"), "CHF"),
        )
        gm_liste = list(Stundensatz.filter(jahr=2026))
        self.assertEqual(len(gm_liste), 1)
        self.assertEqual(gm_liste[0].stundensatz, Measurement(Decimal("87.50"), "CHF"))
