"""Tests für apps/projekt/models/projekt.py."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from general_manager.measurement import Measurement

from apps.projekt.models import Projekt

_ProjektModel: Any = Projekt.Interface._model  # type: ignore[misc]

_TESTJAHR = 2024
_OFFERTE_STANDARD = Decimal("100000")
_WV_STANDARD = Decimal("90000")
_OFFERTE_KLEIN = Decimal("50000")


class ProjektModelTest(TestCase):
    """Prüft Felder und Constraints des Projekt-Modells."""

    def setUp(self) -> None:
        self.user = User.objects.create_user("tester", password="secret")
        self.projekt = Projekt.create(
            ignore_permission=True,
            name="Testprojekt",
            auftragsnummer="2024-001",
            jahr=_TESTJAHR,
            projektleiter=str(self.user.pk),
            offerte_summe=Measurement(_OFFERTE_STANDARD, "CHF"),
            wv_summe=Measurement(_WV_STANDARD, "CHF"),
        )

    def test_felder_vorhanden(self) -> None:
        feld_namen = {f.name for f in _ProjektModel._meta.get_fields()}
        for feld in (
            "name",
            "auftragsnummer",
            "jahr",
            "projektleiter",
            "offerte_summe",
            "wv_summe",
            "auftrag_fertig",
        ):
            self.assertIn(feld, feld_namen, msg=f"Feld '{feld}' fehlt am Modell")

    def test_bisher_verrechnet_ist_kein_modelfeld(self) -> None:
        feld_namen = {f.name for f in _ProjektModel._meta.get_fields()}
        self.assertNotIn("bisher_verrechnet", feld_namen)

    def test_anlegen_klappt_mit_pflichtfeldern(self) -> None:
        proj = Projekt.create(
            ignore_permission=True,
            name="Weiteres Projekt",
            auftragsnummer="2024-002",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_KLEIN, "CHF"),
        )
        self.assertIsNotNone(proj.id)

    def test_auftragsnummer_muss_eindeutig_sein(self) -> None:
        from django.db import IntegrityError

        with self.assertRaises((IntegrityError, ValidationError)):
            Projekt.create(
                ignore_permission=True,
                name="Duplikat",
                auftragsnummer="2024-001",
                jahr=_TESTJAHR,
                offerte_summe=Measurement(_OFFERTE_KLEIN, "CHF"),
            )

    def test_projektleiter_ist_optional(self) -> None:
        proj = Projekt.create(
            ignore_permission=True,
            name="Ohne Leiter",
            auftragsnummer="2024-003",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_KLEIN, "CHF"),
        )
        self.assertIsNone(proj.projektleiter)

    def test_wv_summe_ist_nullable(self) -> None:
        proj = Projekt.create(
            ignore_permission=True,
            name="Ohne WV",
            auftragsnummer="2024-004",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_KLEIN, "CHF"),
            wv_summe=None,
        )
        self.assertIsNone(proj.wv_summe)

    def test_auftrag_fertig_default_ist_false(self) -> None:
        proj = Projekt.create(
            ignore_permission=True,
            name="Standard Flags 2",
            auftragsnummer="2024-006",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_KLEIN, "CHF"),
        )
        self.assertFalse(proj.auftrag_fertig)

    def test_create_mit_projektleiter_als_string_id(self) -> None:
        """create() konvertiert projektleiter:'2' → projektleiter_id=2."""
        user = User.objects.create_user("pl2", password="secret")
        proj = Projekt.create(
            name="String-PL-Test",
            auftragsnummer="2024-PL",
            jahr=str(_TESTJAHR),
            offerte_summe=Measurement(Decimal("10000"), "CHF"),
            wv_summe=Measurement(Decimal("9000"), "CHF"),
            projektleiter=str(user.pk),
            ignore_permission=True,
        )
        self.assertEqual(proj.projektleiter.pk, user.pk)  # type: ignore[union-attr]

    def test_create_ohne_projektleiter(self) -> None:
        proj = Projekt.create(
            name="Ohne PL",
            auftragsnummer="2024-NPL",
            jahr=str(_TESTJAHR),
            offerte_summe=Measurement(Decimal("10000"), "CHF"),
            wv_summe=Measurement(Decimal("9000"), "CHF"),
            ignore_permission=True,
        )
        self.assertIsNone(proj.projektleiter)

    def test_update_mit_projektleiter_als_string_id(self) -> None:
        """update() konvertiert projektleiter:'x' → projektleiter_id=x."""
        user = User.objects.create_user("pl3", password="secret")
        proj = Projekt.create(
            name="Update-PL-Test",
            auftragsnummer="2024-UPL",
            jahr=str(_TESTJAHR),
            offerte_summe=Measurement(Decimal("10000"), "CHF"),
            wv_summe=Measurement(Decimal("9000"), "CHF"),
            ignore_permission=True,
        )
        updated = proj.update(projektleiter=str(user.pk), ignore_permission=True)
        self.assertEqual(updated.projektleiter.pk, user.pk)  # type: ignore[union-attr]
        cleared = updated.update(projektleiter=None, ignore_permission=True)
        self.assertIsNone(cleared.projektleiter)


class ProjektRegelnTest(TestCase):
    """Prüft die Validierungsregeln des Projekt-Modells."""

    def _erstelle_db_obj(self, **kwargs: Any) -> Any:
        defaults = dict(
            name="Regeltest",
            auftragsnummer="R-001",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_STANDARD, "CHF"),
            wv_summe=Measurement(_WV_STANDARD, "CHF"),
        )
        defaults.update(kwargs)
        return _ProjektModel(**defaults)

    def test_offerte_summe_null_schlaegt_fehl(self) -> None:
        obj = self._erstelle_db_obj(offerte_summe=Measurement(Decimal("0"), "CHF"))
        with self.assertRaises((ValidationError, Exception)):
            obj.full_clean()

    def test_wv_summe_null_schlaegt_fehl(self) -> None:
        obj = self._erstelle_db_obj(wv_summe=Measurement(Decimal("0"), "CHF"))
        with self.assertRaises((ValidationError, Exception)):
            obj.full_clean()

    def test_wv_summe_none_ist_gueltig(self) -> None:
        obj = Projekt.create(
            ignore_permission=True,
            name="Ohne WV",
            auftragsnummer="R-002",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_STANDARD, "CHF"),
            wv_summe=None,
        )
        self.assertIsNotNone(obj.id)

    def test_offerte_groesser_wv_ist_gueltig(self) -> None:
        obj = Projekt.create(
            ignore_permission=True,
            name="Offerte > WV",
            auftragsnummer="R-003",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_STANDARD, "CHF"),
            wv_summe=Measurement(Decimal("80000"), "CHF"),
        )
        self.assertIsNotNone(obj.id)

    def test_wv_groesser_offerte_ist_gueltig(self) -> None:
        obj = Projekt.create(
            ignore_permission=True,
            name="WV > Offerte",
            auftragsnummer="R-004",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(Decimal("80000"), "CHF"),
            wv_summe=Measurement(_OFFERTE_STANDARD, "CHF"),
        )
        self.assertIsNotNone(obj.id)
