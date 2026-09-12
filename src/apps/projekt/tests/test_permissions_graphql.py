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

PROJEKT_LISTE_QUERY = """
query {
  projektList {
    items {
      name
      offerteSumme { value }
      wvSumme { value }
    }
    pageInfo { totalCount }
  }
}
"""

PROJEKT_DETAIL_QUERY = """
query ($id: ID!) {
  projekt(id: $id) {
    name
    offerteSumme { value }
    kostenPositionenList { items { id } }
    projektKennzahlenList { items { summeOfferteKosten { value } } }
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


class ProjektSichtbarkeitTest(RollenGraphQLTestBase):
    """Projektliste und -detail je Rolle."""

    def _liste(self) -> Any:
        return self._gql(PROJEKT_LISTE_QUERY)["projektList"]

    def _detail(self) -> Any:
        return self._gql(PROJEKT_DETAIL_QUERY, {"id": str(self.projekt.id)})["projekt"]

    def test_monteur_sieht_projekt_ohne_summen(self) -> None:
        self._login("Monteur")
        liste = self._liste()
        self.assertEqual(liste["pageInfo"]["totalCount"], 1)
        item = liste["items"][0]
        self.assertEqual(item["name"], "Sichtbarkeitsprojekt")
        self.assertIsNone(item["offerteSumme"])
        self.assertIsNone(item["wvSumme"])

    def test_monteur_sieht_keine_kostenpositionen(self) -> None:
        self._login("Monteur")
        self.assertEqual(self._detail()["kostenPositionenList"]["items"], [])

    def test_betrachter_sieht_summen_aber_keine_kostenpositionen(self) -> None:
        self._login("Betrachter")
        detail = self._detail()
        self.assertEqual(detail["offerteSumme"]["value"], 100000.0)
        self.assertEqual(detail["kostenPositionenList"]["items"], [])
        self.assertNotEqual(detail["projektKennzahlenList"]["items"], [])

    def test_projektleiter_sieht_alles(self) -> None:
        self._login("Projektleiter")
        detail = self._detail()
        self.assertEqual(detail["offerteSumme"]["value"], 100000.0)
        self.assertNotEqual(detail["kostenPositionenList"]["items"], [])
        self.assertNotEqual(detail["projektKennzahlenList"]["items"], [])

    def test_admin_sieht_alles(self) -> None:
        self._login("Admin")
        detail = self._detail()
        self.assertEqual(detail["offerteSumme"]["value"], 100000.0)
        self.assertNotEqual(detail["kostenPositionenList"]["items"], [])
        self.assertNotEqual(detail["projektKennzahlenList"]["items"], [])

    def test_anonym_sieht_keine_projekte(self) -> None:
        self.assertEqual(self._liste()["pageInfo"]["totalCount"], 0)


CREATE_KOSTEN_POSITION = """
mutation ($projekt: ID!, $art: ID!, $wert: MeasurementScalar) {
  createKostenPosition(projekt: $projekt, art: $art, offerteKostenWert: $wert) {
    success
  }
}
"""

UPDATE_KOSTEN_POSITION = """
mutation ($id: Int!, $wert: MeasurementScalar) {
  updateKostenPosition(id: $id, offerteKostenWert: $wert) { success }
}
"""

DELETE_KOSTEN_POSITION = """
mutation ($id: Int!) { deleteKostenPosition(id: $id) { success } }
"""


class KostenPositionMutationsTest(RollenGraphQLTestBase):
    """Schreibzugriff auf Kostenpositionen je Rolle.

    Diese Tests decken eine Lücke ab, die lange offenstand: über GraphQL konnte
    ein Monteur Kostenpositionen anlegen. `__based_on__ = "projekt"` sah wie
    Schutz aus, ist bei Create-Mutationen aber wirkungslos — die Mutation-Schicht
    schreibt `projekt` vorher auf `projekt_id` um, die Delegation findet ihre
    Basis nicht mehr und fällt auf DEFAULT_PERMISSIONS zurück (reference.md §5).
    Die Suite war damals grün, weil alle Tests mit `ignore_permission=True`
    schreiben und den GraphQL-Pfad nie berührten.

    Deshalb prüfen die Negativ-Tests hier nicht nur den Fehlercode, sondern auch,
    dass wirklich nichts in der Datenbank gelandet ist.
    """

    def setUp(self) -> None:
        super().setUp()
        freie_art = Kostenart.filter(schluessel="regulierung").first()
        assert isinstance(freie_art, Kostenart)
        self.freie_art = freie_art
        vorhandene = KostenPosition.filter(projekt=self.projekt).first()
        assert isinstance(vorhandene, KostenPosition)
        self.vorhandene = vorhandene

    def _mutation(self, query: str, variables: dict[str, Any]) -> tuple[bool, Any]:
        """Gibt (erfolgreich, fehlercode-oder-None) zurück."""
        response = self.client.post(
            "/graphql/",
            data=json.dumps({"query": query, "variables": variables}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        if "errors" in payload:
            return False, payload["errors"][0].get("extensions", {}).get("code")
        return True, None

    def _anlegen(self) -> tuple[bool, Any]:
        return self._mutation(
            CREATE_KOSTEN_POSITION,
            {
                "projekt": str(self.projekt.id),
                "art": str(self.freie_art.id),
                "wert": "500.00 CHF",
            },
        )

    def _anzahl_positionen(self) -> int:
        return len(list(KostenPosition.filter(projekt=self.projekt)))

    # ---------------- Anlegen ----------------

    def test_monteur_darf_keine_kostenposition_anlegen(self) -> None:
        self._login("Monteur")
        vorher = self._anzahl_positionen()
        erfolg, code = self._anlegen()
        self.assertFalse(erfolg)
        self.assertEqual(code, "PERMISSION_DENIED")
        self.assertEqual(self._anzahl_positionen(), vorher)

    def test_betrachter_darf_keine_kostenposition_anlegen(self) -> None:
        self._login("Betrachter")
        vorher = self._anzahl_positionen()
        erfolg, code = self._anlegen()
        self.assertFalse(erfolg)
        self.assertEqual(code, "PERMISSION_DENIED")
        self.assertEqual(self._anzahl_positionen(), vorher)

    def test_anonym_darf_keine_kostenposition_anlegen(self) -> None:
        vorher = self._anzahl_positionen()
        erfolg, code = self._anlegen()
        self.assertFalse(erfolg)
        self.assertEqual(code, "PERMISSION_DENIED")
        self.assertEqual(self._anzahl_positionen(), vorher)

    def test_projektleiter_darf_kostenposition_anlegen(self) -> None:
        self._login("Projektleiter")
        vorher = self._anzahl_positionen()
        erfolg, code = self._anlegen()
        self.assertTrue(erfolg, f"unerwartet abgewiesen: {code}")
        self.assertEqual(self._anzahl_positionen(), vorher + 1)

    def test_admin_darf_kostenposition_anlegen(self) -> None:
        self._login("Admin")
        vorher = self._anzahl_positionen()
        erfolg, code = self._anlegen()
        self.assertTrue(erfolg, f"unerwartet abgewiesen: {code}")
        self.assertEqual(self._anzahl_positionen(), vorher + 1)

    # ---------------- Ändern ----------------

    def test_monteur_darf_kostenposition_nicht_aendern(self) -> None:
        self._login("Monteur")
        erfolg, code = self._mutation(
            UPDATE_KOSTEN_POSITION,
            {"id": int(self.vorhandene.id), "wert": "999.00 CHF"},
        )
        self.assertFalse(erfolg)
        self.assertEqual(code, "PERMISSION_DENIED")
        unveraendert = KostenPosition(id=self.vorhandene.id)
        assert unveraendert.offerte_kosten_wert is not None
        self.assertEqual(
            unveraendert.offerte_kosten_wert.magnitude, Decimal("20000.00")
        )

    def test_projektleiter_darf_kostenposition_aendern(self) -> None:
        self._login("Projektleiter")
        erfolg, code = self._mutation(
            UPDATE_KOSTEN_POSITION,
            {"id": int(self.vorhandene.id), "wert": "999.00 CHF"},
        )
        self.assertTrue(erfolg, f"unerwartet abgewiesen: {code}")

    # ---------------- Löschen ----------------

    def test_monteur_darf_kostenposition_nicht_loeschen(self) -> None:
        self._login("Monteur")
        vorher = self._anzahl_positionen()
        erfolg, code = self._mutation(
            DELETE_KOSTEN_POSITION, {"id": int(self.vorhandene.id)}
        )
        self.assertFalse(erfolg)
        self.assertEqual(code, "PERMISSION_DENIED")
        self.assertEqual(self._anzahl_positionen(), vorher)

    def test_projektleiter_darf_kostenposition_loeschen(self) -> None:
        self._login("Projektleiter")
        vorher = self._anzahl_positionen()
        erfolg, code = self._mutation(
            DELETE_KOSTEN_POSITION, {"id": int(self.vorhandene.id)}
        )
        self.assertTrue(erfolg, f"unerwartet abgewiesen: {code}")
        self.assertEqual(self._anzahl_positionen(), vorher - 1)
