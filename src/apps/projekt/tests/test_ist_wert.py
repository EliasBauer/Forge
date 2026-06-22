"""Tests für apps/projekt/calculation_manager/ist_wert.py."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.test import TestCase
from general_manager.measurement import Measurement

from apps.bexio.models import Konto, Lieferantenrechnung
from apps.projekt.calculation_manager import IstWert
from apps.projekt.models import Kostenart, Projekt

_KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]
_KontoModel: Any = Konto.Interface._model  # type: ignore[misc]
_LieferantenrechnungModel: Any = Lieferantenrechnung.Interface._model  # type: ignore[misc]

_TESTJAHR = 2024
_AUFTRAGSNUMMER = "2024-200"


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
) -> None:
    _LieferantenrechnungModel.objects.create(
        bexio_id=uuid.uuid4(),
        bexio_zeilen_id=uuid.uuid4(),
        dokument_nr=f"R-{uuid.uuid4().hex[:6]}",
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


class IstWertTest(TestCase):
    """Prüft IstWert CalculationInterface."""

    def setUp(self) -> None:
        User.objects.create_user("iw_tester", password="x")
        _lade_kostenart_daten()
        self.projekt = Projekt.create(
            ignore_permission=True,
            name="IstWert-Projekt",
            auftragsnummer=_AUFTRAGSNUMMER,
            jahr=_TESTJAHR,
            offerte_summe=Measurement(Decimal("100000"), "CHF"),
        )
        self.konto_4001 = _konto("4001")

    def _iw(self, schluessel: str) -> IstWert:
        art = Kostenart.filter(schluessel=schluessel).first()
        assert isinstance(art, Kostenart)
        return IstWert(projekt=self.projekt, kostenart=art)

    # --- Frühe Returns ---

    def test_ist_kosten_wert_none_fuer_ertragsblock(self) -> None:
        self.assertIsNone(self._iw("regie").ist_kosten_wert)

    def test_ist_kosten_wert_none_fuer_stunden(self) -> None:
        self.assertIsNone(self._iw("stunden").ist_kosten_wert)

    def test_ist_kosten_wert_none_fuer_transport_montage(self) -> None:
        self.assertIsNone(self._iw("transport_montage").ist_kosten_wert)

    def test_ist_kosten_wert_none_ohne_konto_nummer(self) -> None:
        # nachtrag: ist_ertragsblock=False, konto_nummer=None, nicht diverses/stunden/tm
        self.assertIsNone(self._iw("nachtrag").ist_kosten_wert)

    # --- Konto-Match ---

    def test_ist_kosten_wert_none_ohne_passende_rechnung(self) -> None:
        # konto 4001 (apparate), aber keine Rechnung mit dieser Auftragsnummer
        self.assertIsNone(self._iw("apparate").ist_kosten_wert)

    def test_ist_kosten_wert_konto_match(self) -> None:
        _rechnung(_AUFTRAGSNUMMER, Decimal("1000"), Decimal("77"), self.konto_4001)
        iw = self._iw("apparate")
        self.assertEqual(iw.ist_kosten_wert, Measurement(Decimal("923"), "CHF"))

    def test_ist_kosten_wert_konto_match_mehrere_rechnungen(self) -> None:
        _rechnung(_AUFTRAGSNUMMER, Decimal("500"), Decimal("0"), self.konto_4001)
        _rechnung(_AUFTRAGSNUMMER, Decimal("300"), Decimal("23.1"), self.konto_4001)
        iw = self._iw("apparate")
        self.assertEqual(iw.ist_kosten_wert, Measurement(Decimal("776.90"), "CHF"))

    def test_ist_kosten_wert_ignoriert_anderes_projekt(self) -> None:
        _rechnung("ANDERES-PROJEKT", Decimal("5000"), Decimal("0"), self.konto_4001)
        self.assertIsNone(self._iw("apparate").ist_kosten_wert)

    # --- Diverses ---

    def test_ist_kosten_wert_diverses_none_ohne_rechnungen(self) -> None:
        self.assertIsNone(self._iw("diverses").ist_kosten_wert)

    def test_ist_kosten_wert_diverses_ohne_konto(self) -> None:
        _rechnung(_AUFTRAGSNUMMER, Decimal("200"), Decimal("0"), None)
        iw = self._iw("diverses")
        self.assertEqual(iw.ist_kosten_wert, Measurement(Decimal("200"), "CHF"))

    def test_ist_kosten_wert_diverses_schliesst_bekannte_konten_aus(self) -> None:
        # Rechnung mit bekanntem Konto 4001 darf nicht in diverses auftauchen
        _rechnung(_AUFTRAGSNUMMER, Decimal("1000"), Decimal("0"), self.konto_4001)
        self.assertIsNone(self._iw("diverses").ist_kosten_wert)

    def test_ist_kosten_wert_diverses_unbekanntes_konto_zaehlt(self) -> None:
        unbekannt = _konto("9999")
        _rechnung(_AUFTRAGSNUMMER, Decimal("400"), Decimal("0"), unbekannt)
        iw = self._iw("diverses")
        self.assertEqual(iw.ist_kosten_wert, Measurement(Decimal("400"), "CHF"))

    # --- ist_kosten_wert_prozent ---

    def test_ist_kosten_wert_prozent_none_wenn_kein_wert(self) -> None:
        self.assertIsNone(self._iw("apparate").ist_kosten_wert_prozent)

    def test_ist_kosten_wert_prozent_none_wenn_summe_null(self) -> None:
        # ist_kosten_wert ist None → Prozent auch None
        self.assertIsNone(self._iw("regie").ist_kosten_wert_prozent)

    def test_ist_kosten_wert_prozent_korrekt(self) -> None:
        # apparate: 500 von gesamt 1000 = 50%
        konto_4002 = _konto("4002")
        _rechnung(_AUFTRAGSNUMMER, Decimal("500"), Decimal("0"), self.konto_4001)
        _rechnung(_AUFTRAGSNUMMER, Decimal("500"), Decimal("0"), konto_4002)
        iw = self._iw("apparate")
        self.assertEqual(iw.ist_kosten_wert_prozent, Decimal("50.00"))
