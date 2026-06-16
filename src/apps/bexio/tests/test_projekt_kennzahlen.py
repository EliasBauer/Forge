"""Tests für apps/bexio/calculation_manager/projekt_kennzahlen.py."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.test import TestCase
from general_manager.measurement import Measurement

from apps.bexio.calculation_manager import ProjektKennzahlen
from apps.bexio.models import Lieferantenrechnung
from apps.projekt.models import Kostenart, KostenPosition, Projekt
from apps.stunden.models import Stundensatz

_KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]
_LieferantenrechnungModel: Any = Lieferantenrechnung.Interface._model  # type: ignore[misc]

_TESTJAHR = 2024
_STUNDENSATZ = Decimal("87")
_OFFERTE_STANDARD = Decimal("100000")
_WV_STANDARD = Decimal("90000")
_OFFERTE_KLEIN = Decimal("50000")


def _lade_kostenart_daten() -> None:
    _KostenartModel.objects.bulk_create(
        [_KostenartModel(**item) for item in Kostenart._data],
        ignore_conflicts=True,
    )


class ProjektKennzahlenTest(TestCase):
    """Prüft ProjektKennzahlen CalculationInterface."""

    def setUp(self) -> None:
        self.user = User.objects.create_user("rechner", password="x")
        _lade_kostenart_daten()
        self.projekt = Projekt.create(
            ignore_permission=True,
            name="Berechnungsprojekt",
            auftragsnummer="2024-100",
            jahr=_TESTJAHR,
            projektleiter=str(self.user.pk),
            offerte_summe=Measurement(_OFFERTE_STANDARD, "CHF"),
            wv_summe=Measurement(_WV_STANDARD, "CHF"),
        )
        Stundensatz.create(
            ignore_permission=True,
            jahr=_TESTJAHR,
            stundensatz=Measurement(_STUNDENSATZ, "CHF"),
        )

    def _kz(self, projekt: Projekt | None = None) -> ProjektKennzahlen:
        return ProjektKennzahlen(projekt=projekt or self.projekt)

    def test_summe_wv_plus_gibt_wv_summe_zurueck(self) -> None:
        self.assertEqual(self._kz().summe_wv_plus.magnitude, _WV_STANDARD)
        self.assertEqual(self._kz().summe_wv_plus.unit, "CHF")

    def test_summe_wv_plus_gibt_null_wenn_wv_summe_none(self) -> None:
        proj = Projekt.create(
            ignore_permission=True,
            name="Ohne WV",
            auftragsnummer="2024-101",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_KLEIN, "CHF"),
            wv_summe=None,
        )
        self.assertEqual(self._kz(proj).summe_wv_plus.magnitude, Decimal("0"))

    def test_bisher_verrechnet_ist_null_ohne_bexio(self) -> None:
        self.assertEqual(self._kz().bisher_verrechnet.magnitude, Decimal("0"))

    def test_summe_ist_kosten_ist_null_ohne_bexio(self) -> None:
        self.assertEqual(self._kz().summe_ist_kosten.magnitude, Decimal("0"))

    def test_summe_offerte_kosten_ohne_positionen(self) -> None:
        self.assertEqual(self._kz().summe_offerte_kosten.magnitude, Decimal("0"))

    def test_summe_offerte_kosten_mit_position(self) -> None:
        art = Kostenart.filter(schluessel="regulierung").first()
        assert isinstance(art, Kostenart)
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt.id,
            art_id=art.id,
            offerte_kosten_wert=Measurement(Decimal("20000"), "CHF"),
        )
        self.assertEqual(self._kz().summe_offerte_kosten.magnitude, Decimal("20000.00"))

    def test_summe_offerte_kosten_schliesst_ertragsblock_aus(self) -> None:
        art_regie = Kostenart.filter(schluessel="regie").first()
        art_app = Kostenart.filter(schluessel="apparate").first()
        assert isinstance(art_regie, Kostenart) and isinstance(art_app, Kostenart)
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt.id,
            art_id=art_regie.id,
            offerte_kosten_wert=Measurement(Decimal("10000"), "CHF"),
        )
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt.id,
            art_id=art_app.id,
            offerte_kosten_wert=Measurement(Decimal("30000"), "CHF"),
        )
        self.assertEqual(self._kz().summe_offerte_kosten.magnitude, Decimal("30000.00"))

    def test_summe_wv_kosten_schliesst_ertragsblock_aus(self) -> None:
        art_regie = Kostenart.filter(schluessel="regie").first()
        art_app = Kostenart.filter(schluessel="apparate").first()
        assert isinstance(art_regie, Kostenart) and isinstance(art_app, Kostenart)
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt.id,
            art_id=art_regie.id,
            offerte_kosten_wert=Measurement(Decimal("5000"), "CHF"),
        )
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt.id,
            art_id=art_app.id,
            offerte_kosten_wert=Measurement(Decimal("50000"), "CHF"),
        )
        kz = self._kz()
        self.assertGreater(kz.summe_wv_kosten.magnitude, Decimal("0"))
        self.assertEqual(kz.summe_offerte_kosten.magnitude, Decimal("50000.00"))

    def test_verbrauchsrate_none_ohne_offerte(self) -> None:
        self.assertIsNone(self._kz().verbrauchsrate)

    def test_delta_wv_off_none_ohne_offerte(self) -> None:
        self.assertIsNone(self._kz().delta_wv_off)

    def test_delta_wv_off_pct_none_ohne_offerte(self) -> None:
        self.assertIsNone(self._kz().delta_wv_off_pct)

    def test_delta_ist_plan_none_ohne_wv_kosten(self) -> None:
        self.assertIsNone(self._kz().delta_ist_plan)

    def test_delta_ist_plan_pct_none_ohne_wv_kosten(self) -> None:
        self.assertIsNone(self._kz().delta_ist_plan_pct)

    def test_summe_offerte_kosten_null_wenn_offerte_wert_none(self) -> None:
        art = Kostenart.filter(schluessel="regulierung").first()
        assert isinstance(art, Kostenart)
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt.id,
            art_id=art.id,
            offerte_kosten_wert=None,
        )
        self.assertEqual(self._kz().summe_offerte_kosten.magnitude, Decimal("0.00"))

    def test_summe_wv_kosten_null_wenn_wv_kosten_wert_none(self) -> None:
        proj_ohne_wv = Projekt.create(
            ignore_permission=True,
            name="Ohne WV 2",
            auftragsnummer="2024-102",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_KLEIN, "CHF"),
            wv_summe=None,
        )
        art = Kostenart.filter(schluessel="regulierung").first()
        assert isinstance(art, Kostenart)
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=proj_ohne_wv.id,
            art_id=art.id,
            offerte_kosten_wert=Measurement(Decimal("10000"), "CHF"),
        )
        kz = self._kz(proj_ohne_wv)
        self.assertEqual(kz.summe_wv_kosten.magnitude, Decimal("0.00"))

    def test_summe_ist_kosten_mit_rechnung(self) -> None:
        _LieferantenrechnungModel.objects.create(
            bexio_id=uuid.uuid4(),
            bexio_zeilen_id=uuid.uuid4(),
            dokument_nr="2024-R-001",
            titel="Testrechnung",
            richtiger_titel=self.projekt.auftragsnummer,
            status="paid",
            rechnungsdatum=date(2024, 1, 15),
            lieferant_id=1,
            firmenname="Testlieferant AG",
            waehrung_code="CHF",
            rechnungsbetrag=Decimal("1000.00"),
            ausstehender_betrag=Decimal("0.00"),
            bexio_erstellt_am=datetime(2024, 1, 15, 10, 0, 0),
            betrag=Decimal("1000.00"),
            steuer_berechnet=Decimal("77.00"),
        )
        self.assertEqual(self._kz().summe_ist_kosten.magnitude, Decimal("923.00"))
