"""Tests für apps/projekt/models/projekt_phase.py."""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError
from django.test import TestCase

from apps.projekt.models import ProjektPhase

_ProjektPhaseModel: Any = ProjektPhase.Interface._model  # type: ignore[misc]


class ProjektPhaseDatenTest(TestCase):
    """Prüft den statischen _data-Katalog von ProjektPhase."""

    def setUp(self) -> None:
        _ProjektPhaseModel.objects.bulk_create(
            [_ProjektPhaseModel(**item) for item in ProjektPhase._data],
            ignore_conflicts=True,
        )

    def test_alle_3_eintraege_vorhanden(self) -> None:
        self.assertEqual(ProjektPhase.filter().count(), 3)

    def test_namen_sind_offen_in_arbeit_fertig(self) -> None:
        namen = {phase.name for phase in ProjektPhase.filter()}
        self.assertEqual(namen, {"Offen", "In Arbeit", "Fertig"})

    def test_name_unique_constraint(self) -> None:
        with self.assertRaises(IntegrityError):
            _ProjektPhaseModel.objects.create(name="Offen")

    def test_str_gibt_name_zurueck(self) -> None:
        phase = ProjektPhase.filter(name="Offen").first()
        assert phase is not None
        self.assertEqual(str(phase), "Offen")
