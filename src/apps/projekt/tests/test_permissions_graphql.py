"""Rollenabhängige Sichtbarkeit über GraphQL (Admin/Projektleiter/Betrachter/
Monteur)."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import Group, User
from django.test import TestCase
from general_manager.measurement import Measurement

from apps.projekt.models import Kostenart, KostenPosition, Projekt, ProjektStatus

_KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]

_TESTJAHR = 2024

KENNZAHLEN_QUERY = """
query {
  projektKennzahlenList {
    items {
      summeOfferteKosten { value }
    }
  }
}
"""

IST_WERT_QUERY = """
query {
  istWertList {
    items {
      kostenart { schluessel }
    }
  }
}
"""


def _lade_kostenart_daten() -> None:
    _KostenartModel.objects.bulk_create(
        [_KostenartModel(**item) for item in Kostenart._data],
        ignore_conflicts=True,
    )


def _offen() -> ProjektStatus:
    status = ProjektStatus.filter(name="Offen").first()
    assert status is not None
    return status


class RollenGraphQLTestBase(TestCase):
    """Ein Projekt mit einer Kostenposition plus Login- und GraphQL-Helfer."""

    def setUp(self) -> None:
        _lade_kostenart_daten()
        self.projekt = Projekt.create(
            ignore_permission=True,
            projekt_status=_offen(),
            name="Sichtbarkeitsprojekt",
            auftragsnummer="2024-900",
            jahr=_TESTJAHR,
            offerte_summe=Measurement(Decimal("100000"), "CHF"),
            wv_summe=Measurement(Decimal("90000"), "CHF"),
        )
        art = Kostenart.filter(schluessel="apparate").first()
        assert isinstance(art, Kostenart)
        KostenPosition.create(
            ignore_permission=True,
            projekt_id=self.projekt.id,
            art_id=art.id,
            offerte_kosten_wert=Measurement(Decimal("20000"), "CHF"),
        )

    def _login(self, gruppe: str) -> None:
        user = User.objects.create_user(f"u_{gruppe.lower()}", password="x")
        group, _ = Group.objects.get_or_create(name=gruppe)
        user.groups.add(group)
        self.client.force_login(user)

    def _gql(self, query: str, variables: dict[str, Any] | None = None) -> Any:
        response = self.client.post(
            "/graphql/",
            data=json.dumps({"query": query, "variables": variables or {}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        return payload["data"]


class CalculationManagerSichtbarkeitTest(RollenGraphQLTestBase):
    """projektKennzahlenList/istWertList dürfen nur Berechtigte lesen."""

    def _kennzahlen(self) -> list[Any]:
        items: list[Any] = self._gql(KENNZAHLEN_QUERY)["projektKennzahlenList"]["items"]
        return items

    def _ist_werte(self) -> list[Any]:
        items: list[Any] = self._gql(IST_WERT_QUERY)["istWertList"]["items"]
        return items

    def test_anonym_sieht_keine_kennzahlen(self) -> None:
        self.assertEqual(self._kennzahlen(), [])

    def test_anonym_sieht_keine_ist_werte(self) -> None:
        self.assertEqual(self._ist_werte(), [])

    def test_monteur_sieht_keine_kennzahlen(self) -> None:
        self._login("Monteur")
        self.assertEqual(self._kennzahlen(), [])

    def test_monteur_sieht_keine_ist_werte(self) -> None:
        self._login("Monteur")
        self.assertEqual(self._ist_werte(), [])

    def test_betrachter_sieht_kennzahlen(self) -> None:
        self._login("Betrachter")
        self.assertNotEqual(self._kennzahlen(), [])

    def test_betrachter_sieht_keine_ist_werte(self) -> None:
        self._login("Betrachter")
        self.assertEqual(self._ist_werte(), [])

    def test_projektleiter_sieht_kennzahlen_und_ist_werte(self) -> None:
        self._login("Projektleiter")
        self.assertNotEqual(self._kennzahlen(), [])
        self.assertNotEqual(self._ist_werte(), [])

    def test_admin_sieht_kennzahlen_und_ist_werte(self) -> None:
        self._login("Admin")
        self.assertNotEqual(self._kennzahlen(), [])
        self.assertNotEqual(self._ist_werte(), [])
