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
        # transport_montage_fremd: ist_ertragsblock=False, konto_nummer=None,
        # nicht diverses/stunden/transport_montage -> prueft den Zweig
        # "konto_nr is None" in _rechnungen (nicht den Ertragsblock-Return).
        self.assertEqual(self._iw("transport_montage_fremd").rechnungen, [])

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
