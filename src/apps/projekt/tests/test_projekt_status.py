"""Tests für apps/projekt/models/projekt_status.py."""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError
from django.test import TestCase

from apps.projekt.models import ProjektStatus

_ProjektStatusModel: Any = ProjektStatus.Interface._model  # type: ignore[misc]


class ProjektStatusDatenTest(TestCase):
    """Prüft den statischen _data-Katalog von ProjektStatus."""

    def setUp(self) -> None:
        _ProjektStatusModel.objects.bulk_create(
            [_ProjektStatusModel(**item) for item in ProjektStatus._data],
            ignore_conflicts=True,
        )

    def test_alle_3_eintraege_vorhanden(self) -> None:
        self.assertEqual(ProjektStatus.filter().count(), 3)

    def test_namen_sind_offen_in_arbeit_fertig(self) -> None:
        namen = {s.name for s in ProjektStatus.filter()}
        self.assertEqual(namen, {"Offen", "In Arbeit", "Fertig"})

    def test_name_unique_constraint(self) -> None:
        with self.assertRaises(IntegrityError):
            _ProjektStatusModel.objects.create(name="Offen")
