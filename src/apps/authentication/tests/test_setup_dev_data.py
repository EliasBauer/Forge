"""Tests für das Management-Command setup_dev_data (Demo-Projekte)."""

from __future__ import annotations

import re
from decimal import Decimal
from io import StringIO
from typing import Any

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.bexio.models import Lieferantenrechnung
from apps.projekt.models import Kostenart, KostenPosition, Projekt
from apps.stunden.models import Stundensatz

_KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]

_ERWARTETE_PROJEKTE = 10
_AUFTRAGSNUMMER_MUSTER = re.compile(r"^(\d{4})\.(\d{4})$")
_MIN_POSITIONEN_PRO_PROJEKT = 5


def _lade_kostenart_daten() -> None:
    _KostenartModel.objects.bulk_create(
        [_KostenartModel(**item) for item in Kostenart._data],
        ignore_conflicts=True,
    )


@override_settings(BEXIO_DEV_MODE=True)
class SetupDevDataProjekteTest(TestCase):
    def setUp(self) -> None:
        _lade_kostenart_daten()
        call_command("setup_dev_data", stdout=StringIO())

    def test_legt_zehn_projekte_an(self) -> None:
        self.assertEqual(len(list(Projekt.all())), _ERWARTETE_PROJEKTE)

    def test_auftragsnummer_folgt_jahr_punkt_laufnummer(self) -> None:
        for projekt in Projekt.all():
            match = _AUFTRAGSNUMMER_MUSTER.match(projekt.auftragsnummer)
            self.assertIsNotNone(match, msg=projekt.auftragsnummer)
            assert match is not None
            self.assertEqual(int(match.group(1)), projekt.jahr)

    def test_jedes_projekt_hat_kostenpositionen(self) -> None:
        for projekt in Projekt.all():
            positionen = list(KostenPosition.filter(projekt=projekt))
            self.assertGreaterEqual(
                len(positionen),
                _MIN_POSITIONEN_PRO_PROJEKT,
                msg=projekt.auftragsnummer,
            )

    def test_offerte_summe_entspricht_summe_der_positionen(self) -> None:
        for projekt in Projekt.all():
            summe = Decimal("0")
            for pos in KostenPosition.filter(projekt=projekt):
                if pos.art.ist_ertragsblock or pos.art.schluessel == "stunden":
                    continue
                if pos.offerte_kosten_wert is not None:
                    summe += Decimal(pos.offerte_kosten_wert.magnitude)
            self.assertEqual(
                Decimal(projekt.offerte_summe.magnitude),
                summe,
                msg=projekt.auftragsnummer,
            )

    def test_alle_phasen_kommen_vor(self) -> None:
        phasen = {p.projekt_phase.name for p in Projekt.all()}
        self.assertEqual(phasen, {"Offen", "In Arbeit", "Fertig"})

    def test_stundensatz_fuer_jedes_projektjahr(self) -> None:
        jahre_projekte = {p.jahr for p in Projekt.all()}
        jahre_stundensatz = {s.jahr for s in Stundensatz.all()}
        self.assertTrue(jahre_projekte <= jahre_stundensatz)

    def test_bexio_rechnungen_treffen_projekte(self) -> None:
        nummern = {p.auftragsnummer for p in Projekt.all()}
        getroffen = {
            r.richtiger_titel
            for r in Lieferantenrechnung.all()
            if r.richtiger_titel in nummern
        }
        self.assertGreaterEqual(len(getroffen), 2)

    def test_zweiter_lauf_ist_idempotent(self) -> None:
        call_command("setup_dev_data", stdout=StringIO())
        self.assertEqual(len(list(Projekt.all())), _ERWARTETE_PROJEKTE)
        self.assertEqual(
            len(list(Stundensatz.all())), len({p.jahr for p in Projekt.all()})
        )
        anzahl_positionen = len(list(KostenPosition.all()))
        call_command("setup_dev_data", stdout=StringIO())
        self.assertEqual(len(list(KostenPosition.all())), anzahl_positionen)
