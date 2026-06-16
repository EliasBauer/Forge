"""Tests für apps/projekt/models/kostenart.py."""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError
from django.test import TestCase

from apps.projekt.models import Kostenart

_KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]


class KostenartDatenTest(TestCase):
    """Prüft den statischen _data-Katalog der Kostenart."""

    def setUp(self) -> None:
        _KostenartModel.objects.bulk_create(
            [_KostenartModel(**item) for item in Kostenart._data],
            ignore_conflicts=True,
        )

    def test_alle_15_eintraege_vorhanden(self) -> None:
        self.assertEqual(Kostenart.filter().count(), 15)

    def test_ertragsblock_eintraege_sind_2(self) -> None:
        ertragsblock = [k.schluessel for k in Kostenart.filter(ist_ertragsblock=True)]
        erwartet = {"regie", "nachtrag"}
        self.assertEqual(len(ertragsblock), 2)
        self.assertEqual(set(ertragsblock), erwartet)

    def test_nicht_ertragsblock_enthaelt_kernartikel(self) -> None:
        nicht_ertragsblock = {
            k.schluessel for k in Kostenart.filter(ist_ertragsblock=False)
        }
        for schluessel in ("apparate", "stunden", "transport_montage", "gemeinkosten"):
            self.assertIn(schluessel, nicht_ertragsblock)

    def test_reihenfolge_aufsteigend(self) -> None:
        reihenfolgen = [k.reihenfolge for k in Kostenart.filter().sort("reihenfolge")]
        self.assertEqual(reihenfolgen, sorted(reihenfolgen))

    def test_schluessel_unique_constraint(self) -> None:
        with self.assertRaises(IntegrityError):
            _KostenartModel.objects.create(
                schluessel="apparate",
                name="Duplikat",
                ist_ertragsblock=False,
                reihenfolge=99,
            )

    def test_schluessel_alle_eindeutig(self) -> None:
        alle = [k.schluessel for k in Kostenart.filter()]
        self.assertEqual(len(alle), len(set(alle)))

    def test_apparate_ist_kein_ertragsblock(self) -> None:
        art = Kostenart.filter(schluessel="apparate").first()
        assert isinstance(art, Kostenart)
        self.assertFalse(art.ist_ertragsblock)

    def test_reihenfolge_gemeinkosten_ist_15(self) -> None:
        art = Kostenart.filter(schluessel="gemeinkosten").first()
        assert isinstance(art, Kostenart)
        self.assertEqual(art.reihenfolge, 15)
