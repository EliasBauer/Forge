"""Tests für apps/projekt/models/kosten_position.py."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from general_manager.measurement import Measurement

from apps.projekt.models import Kostenart, KostenPosition, Projekt
from apps.stunden.models import Stundensatz

_KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]
_ProjektModel: Any = Projekt.Interface._model  # type: ignore[misc]
_KostenPositionModel: Any = KostenPosition.Interface._model  # type: ignore[misc]
_StundensatzModel: Any = Stundensatz.Interface._model  # type: ignore[misc]

_TESTJAHR = 2024
_STUNDENSATZ = Decimal("87")
_OFFERTE_STANDARD = Decimal("100000")
_WV_STANDARD = Decimal("90000")
_CALC_OFFERTE_SUMME = Decimal("365595")
_CALC_WV_SUMME = Decimal("319220.06")
_TM_OFFERTE = Decimal("25200.42")
_ERWARTETE_STUNDEN = Decimal("289.66")
_REG_OFFERTE = Decimal("238275")
_REG_PROZENT = Decimal("65.17")
_DREI_APP = Decimal("60000")
_DREI_KAN = Decimal("20000")
_DREI_ARM = Decimal("10000")
_DREI_TM = Decimal("90000")


def _lade_kostenart_daten() -> None:
    _KostenartModel.objects.bulk_create(
        [_KostenartModel(**item) for item in Kostenart._data],
        ignore_conflicts=True,
    )


class KostenPositionModelTest(TestCase):
    """Prüft Felder und Constraints des KostenPosition-Modells."""

    def setUp(self) -> None:
        User.objects.create_user("kp_tester", password="x")
        _lade_kostenart_daten()
        self.projekt_db = Projekt.create(
            ignore_permission=True,
            name="KP-Projekt",
            auftragsnummer="KP-001",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_OFFERTE_STANDARD, "CHF"),
        )
        art_apparate = Kostenart.filter(schluessel="apparate").first()
        assert isinstance(art_apparate, Kostenart)
        self.art_apparate = art_apparate
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt_db.id,
            art_id=self.art_apparate.id,
        )

    def test_felder_vorhanden(self) -> None:
        feld_namen = {f.name for f in _KostenPositionModel._meta.get_fields()}
        for feld in ("projekt", "art", "offerte_kosten_wert"):
            self.assertIn(feld, feld_namen, msg=f"Feld '{feld}' fehlt")

    def test_unique_together_projekt_art(self) -> None:
        with self.assertRaises((IntegrityError, ValidationError)):
            KostenPosition.create(
                ignore_permission=True,
                projekt_id=self.projekt_db.id,
                art_id=self.art_apparate.id,
                offerte_kosten_wert=Measurement(Decimal("10000"), "CHF"),
            )

    def test_art_ist_fk_zu_kostenart(self) -> None:
        kp = KostenPosition.filter(
            projekt=self.projekt_db, art=self.art_apparate
        ).first()
        assert isinstance(kp, KostenPosition)
        self.assertIsInstance(kp.art, Kostenart)

    def test_offerte_kosten_wert_nullable(self) -> None:
        kp = KostenPosition.filter(
            projekt=self.projekt_db, art=self.art_apparate
        ).first()
        assert isinstance(kp, KostenPosition)
        kp = kp.update(ignore_permission=True, offerte_kosten_wert=None)
        self.assertIsNone(kp.offerte_kosten_wert)

    def test_art_schluessel_ist_apparate(self) -> None:
        kp = KostenPosition.filter(
            projekt=self.projekt_db, art=self.art_apparate
        ).first()
        assert isinstance(kp, KostenPosition)
        self.assertEqual(kp.art.schluessel, "apparate")


class KostenPositionBerechnungTest(TestCase):
    """
    Prüft alle berechneten Eigenschaften von KostenPosition.

    Projekt: offerte=365595 CHF, wv=319220.06 CHF, jahr=2024
    Stundensatz: 87 CHF/h (2024)
    """

    def setUp(self) -> None:
        User.objects.create_user("berechner", password="x")
        _lade_kostenart_daten()
        self.projekt_db = Projekt.create(
            ignore_permission=True,
            name="Berechnungsprojekt",
            auftragsnummer="CALC-001",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_CALC_OFFERTE_SUMME, "CHF"),
            wv_summe=Measurement(_CALC_WV_SUMME, "CHF"),
        )
        Stundensatz.create(
            ignore_permission=True,
            jahr=_TESTJAHR,
            stundensatz=Measurement(_STUNDENSATZ, "CHF"),
        )

    _UNSET: object = object()

    def _kp(
        self,
        schluessel: str,
        offerte: Decimal | None | object = _UNSET,
    ) -> KostenPosition:
        art = Kostenart.filter(schluessel=schluessel).first()
        assert isinstance(art, Kostenart)
        kp = KostenPosition.filter(projekt=self.projekt_db, art=art).first()
        if kp is None:
            kp = KostenPosition.create(
                ignore_permission=True,
                projekt_id=self.projekt_db.id,
                art_id=art.id,
            )
        if offerte is not self._UNSET:
            kp = kp.update(
                ignore_permission=True,
                offerte_kosten_wert=(
                    Measurement(offerte, "CHF")  # type: ignore[arg-type]
                    if offerte is not None
                    else None
                ),
            )
        return kp

    # --- offerte_stunden ---

    def test_offerte_stunden_transport_montage_zu_stunden(self) -> None:
        """TM=25200.42 CHF / 87 CHF = 289.66 Stunden."""
        self._kp("transport_montage", _TM_OFFERTE)
        kp_stunden = self._kp("stunden")
        self.assertEqual(kp_stunden.offerte_stunden, _ERWARTETE_STUNDEN)

    def test_offerte_stunden_none_fuer_nicht_stunden_position(self) -> None:
        kp = self._kp("apparate", Decimal("50000"))
        self.assertIsNone(kp.offerte_stunden)

    def test_offerte_stunden_none_ohne_tm_position(self) -> None:
        kp = self._kp("stunden")
        self.assertIsNone(kp.offerte_stunden)

    def test_offerte_stunden_none_ohne_stundensatz(self) -> None:
        _StundensatzModel.objects.filter(jahr=_TESTJAHR).delete()
        self._kp("transport_montage", _TM_OFFERTE)
        kp_stunden = self._kp("stunden")
        self.assertIsNone(kp_stunden.offerte_stunden)

    # --- offerte_kosten_wert_prozent ---

    def test_offerte_kosten_wert_prozent_regulierung(self) -> None:
        """238275 / 365595 * 100 = 65.17%."""
        kp = self._kp("regulierung", _REG_OFFERTE)
        self.assertEqual(kp.offerte_kosten_wert_prozent, _REG_PROZENT)

    def test_offerte_kosten_wert_prozent_none_wenn_kein_wert(self) -> None:
        kp = self._kp("regulierung", None)
        self.assertIsNone(kp.offerte_kosten_wert_prozent)

    def test_offerte_kosten_wert_prozent_none_wenn_offerte_summe_null(self) -> None:
        proj_null = Projekt.create(
            ignore_permission=True,
            name="Null-Offerte",
            auftragsnummer="CALC-002",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(Decimal("1"), "CHF"),
        )
        _ProjektModel.objects.filter(pk=proj_null.id).update(
            offerte_summe_value=Decimal("0")
        )
        art = Kostenart.filter(schluessel="regulierung").first()
        assert isinstance(art, Kostenart)
        kp_obj = KostenPosition.create(
            ignore_permission=True,
            projekt_id=proj_null.id,
            art_id=art.id,
        )
        kp = kp_obj.update(
            ignore_permission=True,
            offerte_kosten_wert=Measurement(Decimal("5000"), "CHF"),
        )
        self.assertIsNone(kp.offerte_kosten_wert_prozent)

    # --- wv_kosten_wert (Standard: proportional) ---

    def test_wv_kosten_wert_proportional_fuer_regulierung(self) -> None:
        """238275 / 365595 * 319220.06 = 208050.33 CHF."""
        kp = self._kp("regulierung", _REG_OFFERTE)
        self.assertEqual(kp.wv_kosten_wert, Measurement(Decimal("208050.33"), "CHF"))

    def test_wv_kosten_wert_none_wenn_offerte_kosten_wert_none(self) -> None:
        kp = self._kp("regulierung", None)
        self.assertIsNone(kp.wv_kosten_wert)

    def test_wv_kosten_wert_none_wenn_offerte_summe_null(self) -> None:
        proj_null = Projekt.create(
            ignore_permission=True,
            name="Null-Offerte 2",
            auftragsnummer="CALC-003",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(Decimal("1"), "CHF"),
            wv_summe=Measurement(_WV_STANDARD, "CHF"),
        )
        _ProjektModel.objects.filter(pk=proj_null.id).update(
            offerte_summe_value=Decimal("0")
        )
        art = Kostenart.filter(schluessel="regulierung").first()
        assert isinstance(art, Kostenart)
        kp_obj = KostenPosition.create(
            ignore_permission=True,
            projekt_id=proj_null.id,
            art_id=art.id,
        )
        kp = kp_obj.update(
            ignore_permission=True,
            offerte_kosten_wert=Measurement(Decimal("5000"), "CHF"),
        )
        self.assertIsNone(kp.wv_kosten_wert)

    def test_wv_kosten_wert_none_wenn_wv_summe_none(self) -> None:
        proj_ohne_wv = Projekt.create(
            ignore_permission=True,
            name="Ohne WV",
            auftragsnummer="CALC-004",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_CALC_OFFERTE_SUMME, "CHF"),
            wv_summe=None,
        )
        art = Kostenart.filter(schluessel="regulierung").first()
        assert isinstance(art, Kostenart)
        kp_obj = KostenPosition.create(
            ignore_permission=True,
            projekt_id=proj_ohne_wv.id,
            art_id=art.id,
        )
        kp = kp_obj.update(
            ignore_permission=True,
            offerte_kosten_wert=Measurement(Decimal("50000"), "CHF"),
        )
        self.assertIsNone(kp.wv_kosten_wert)

    # --- wv_kosten_wert (Ausnahme: stunden) ---

    def test_wv_kosten_wert_stunden_gleich_offerte_stunden(self) -> None:
        self._kp("transport_montage", _TM_OFFERTE)
        kp = self._kp("stunden")
        self.assertEqual(kp.wv_kosten_wert.magnitude, kp.offerte_stunden)

    # --- wv_kosten_wert (Ausnahme: transport_montage) ---

    def test_wv_kosten_wert_transport_montage_gleich_offerte_kosten_wert(self) -> None:
        kp = self._kp("transport_montage", _TM_OFFERTE)
        self.assertEqual(kp.wv_kosten_wert, Measurement(_TM_OFFERTE, "CHF"))

    def test_wv_kosten_wert_transport_montage_fremd_gleich_offerte_kosten_wert(
        self,
    ) -> None:
        kp = self._kp("transport_montage_fremd", Decimal("15000"))
        self.assertEqual(kp.wv_kosten_wert, Measurement(Decimal("15000"), "CHF"))

    def test_wv_kosten_wert_transport_montage_none_wenn_offerte_none(self) -> None:
        kp = self._kp("transport_montage", None)
        self.assertIsNone(kp.wv_kosten_wert)

    # --- wv_kosten_wert (Drei-Positionen: apparate) ---

    def test_wv_kosten_wert_apparate_ohne_tm_proportional(self) -> None:
        """Ohne TM fällt delta_tm = 0 → 60000 / 365595 * 319220.06 = 52389.13 CHF."""
        kp = self._kp("apparate", _DREI_APP)
        self.assertEqual(kp.wv_kosten_wert, Measurement(Decimal("52389.13"), "CHF"))

    def test_wv_kosten_wert_apparate_mit_tm_delta_korrekt(self) -> None:
        """apparate=60000, kanaele=20000, armaturen=10000, tm=90000 → 44778.26 CHF."""
        self._kp("transport_montage", _DREI_TM)
        self._kp("kanaele_rohre", _DREI_KAN)
        self._kp("armaturen", _DREI_ARM)
        kp = self._kp("apparate", _DREI_APP)
        self.assertEqual(kp.wv_kosten_wert, Measurement(Decimal("44778.26"), "CHF"))

    def test_wv_kosten_wert_kanaele_rohre_mit_tm(self) -> None:
        """Kanaele mit TM-Delta → 14926.09 CHF."""
        self._kp("transport_montage", _DREI_TM)
        self._kp("apparate", _DREI_APP)
        self._kp("armaturen", _DREI_ARM)
        kp = self._kp("kanaele_rohre", _DREI_KAN)
        self.assertEqual(kp.wv_kosten_wert, Measurement(Decimal("14926.09"), "CHF"))

    def test_wv_kosten_wert_armaturen_mit_tm(self) -> None:
        """Armaturen mit TM-Delta → 7463.04 CHF."""
        self._kp("transport_montage", _DREI_TM)
        self._kp("apparate", _DREI_APP)
        self._kp("kanaele_rohre", _DREI_KAN)
        kp = self._kp("armaturen", _DREI_ARM)
        self.assertEqual(kp.wv_kosten_wert, Measurement(Decimal("7463.04"), "CHF"))

    def test_wv_kosten_wert_apparate_none_wenn_wv_summe_none(self) -> None:
        proj_ohne_wv = Projekt.create(
            ignore_permission=True,
            name="Ohne WV App",
            auftragsnummer="CALC-010",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_CALC_OFFERTE_SUMME, "CHF"),
            wv_summe=None,
        )
        art_tm = Kostenart.filter(schluessel="transport_montage").first()
        assert isinstance(art_tm, Kostenart)
        kp_tm = KostenPosition.create(
            ignore_permission=True,
            projekt_id=proj_ohne_wv.id,
            art_id=art_tm.id,
        )
        kp_tm.update(
            ignore_permission=True,
            offerte_kosten_wert=Measurement(Decimal("30000"), "CHF"),
        )
        art_app = Kostenart.filter(schluessel="apparate").first()
        assert isinstance(art_app, Kostenart)
        kp_obj = KostenPosition.create(
            ignore_permission=True,
            projekt_id=proj_ohne_wv.id,
            art_id=art_app.id,
        )
        kp = kp_obj.update(
            ignore_permission=True,
            offerte_kosten_wert=Measurement(_DREI_APP, "CHF"),
        )
        self.assertIsNone(kp.wv_kosten_wert)

    def test_wv_kosten_wert_apparate_none_wenn_offerte_summe_null(self) -> None:
        proj_null = Projekt.create(
            ignore_permission=True,
            name="Null-Offerte App",
            auftragsnummer="CALC-011",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(Decimal("1"), "CHF"),
            wv_summe=Measurement(_WV_STANDARD, "CHF"),
        )
        _ProjektModel.objects.filter(pk=proj_null.id).update(
            offerte_summe_value=Decimal("0")
        )
        art_app = Kostenart.filter(schluessel="apparate").first()
        assert isinstance(art_app, Kostenart)
        kp_obj = KostenPosition.create(
            ignore_permission=True,
            projekt_id=proj_null.id,
            art_id=art_app.id,
        )
        kp = kp_obj.update(
            ignore_permission=True,
            offerte_kosten_wert=Measurement(_DREI_APP, "CHF"),
        )
        self.assertIsNone(kp.wv_kosten_wert)

    def test_wv_kosten_wert_apparate_none_wenn_summe_drei_null(self) -> None:
        """summe_der_drei = 0 — apparate ohne Offerte-Wert → wv_kosten_wert ist None."""
        art_app = Kostenart.filter(schluessel="apparate").first()
        assert isinstance(art_app, Kostenart)
        kp = KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt_db.id,
            art_id=art_app.id,
        )
        self.assertIsNone(kp.wv_kosten_wert)

    # --- wv_kosten_wert_prozent ---

    def test_wv_kosten_wert_prozent_gibt_prozentwert_zurueck(self) -> None:
        """208050.33 / 319220.06 * 100 = 65.17%."""
        kp = self._kp("regulierung", _REG_OFFERTE)
        self.assertEqual(kp.wv_kosten_wert_prozent, Decimal("65.17"))

    def test_wv_kosten_wert_prozent_none_wenn_wv_kosten_wert_none(self) -> None:
        kp = self._kp("regulierung", None)
        self.assertIsNone(kp.wv_kosten_wert_prozent)

    def test_wv_kosten_wert_prozent_none_wenn_wv_summe_null(self) -> None:
        proj_null_wv = Projekt.create(
            ignore_permission=True,
            name="WV Summe Null",
            auftragsnummer="CALC-020",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(_CALC_OFFERTE_SUMME, "CHF"),
            wv_summe=Measurement(Decimal("1"), "CHF"),
        )
        _ProjektModel.objects.filter(pk=proj_null_wv.id).update(
            wv_summe_value=Decimal("0")
        )
        art = Kostenart.filter(schluessel="regulierung").first()
        assert isinstance(art, Kostenart)
        kp_obj = KostenPosition.create(
            ignore_permission=True,
            projekt_id=proj_null_wv.id,
            art_id=art.id,
        )
        kp = kp_obj.update(
            ignore_permission=True,
            offerte_kosten_wert=Measurement(Decimal("50000"), "CHF"),
        )
        self.assertIsNone(kp.wv_kosten_wert_prozent)
