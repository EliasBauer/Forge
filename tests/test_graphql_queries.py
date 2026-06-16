"""
Integrationstests: GraphQL-Queries aus frontend/src/graphql/queries.ts

Jeder Test sendet die exakte Query ans /graphql/-Endpoint und prüft:
- HTTP 200
- Keine GraphQL-Fehler in der Antwort
- Erwartete Top-Level-Felder in `data` vorhanden

Ziel: Schema-Drift frühzeitig erkennen, bevor er zur Laufzeit auffällt.
"""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.models import User
from django.test import TestCase
from general_manager.measurement import Measurement

from apps.projekt.models import Kostenart, KostenPosition, Projekt
from apps.stunden.models import Stundensatz

_KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]

GRAPHQL_URL = "/graphql/"


def _gql(
    client: Any, query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    response = client.post(
        GRAPHQL_URL,
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200, (
        f"HTTP {response.status_code}: {response.content[:500]}"
    )
    data: dict[str, Any] = response.json()
    return data


_QUERY_PROJEKT_LISTE = """
    query ProjektListe {
      projektList(pageSize: 100) {
        items {
          id
          auftragsnummer
          name
          offerteSumme { value unit }
          wvSumme { value unit }
          auftragFertig
          projektleiter
          projektKennzahlenList {
            items {
              summeWvPlus { value unit }
              summeIstKosten { value unit }
            }
          }
        }
        pageInfo { totalCount }
      }
    }
"""

_QUERY_PROJEKT_DETAIL = """
    query ProjektDetail($id: ID!) {
      projekt(id: $id) {
        id
        name
        auftragsnummer
        jahr
        offerteSumme { value unit }
        wvSumme { value unit }
        auftragFertig
        projektleiter
        projektKennzahlenList {
          items {
            summeOfferteKosten { value unit }
            summeWvKosten { value unit }
            summeIstKosten { value unit }
            verbrauchsrate
            deltaWvOff { value unit }
            deltaWvOffPct
            deltaIstPlan { value unit }
            deltaIstPlanPct
            summeWvPlus { value unit }
            bisherVerrechnet { value unit }
          }
        }
        kostenPositionenList {
          items {
            id
            art { schluessel }
            offerteKostenWert { value unit }
            offerteStunden
            wvKostenWert { value unit }
            wvKostenWertProzent
            offerteKostenWertProzent
          }
        }
        istWertList {
          items {
            kostenart { schluessel }
            istKostenWert { value unit }
            istKostenWertProzent
          }
        }
      }
    }
"""


class _SharedSetup(TestCase):
    """Erstellt Testdaten einmalig, wird von allen Query-Tests geerbt."""

    def setUp(self) -> None:
        _KostenartModel.objects.bulk_create(
            [_KostenartModel(**item) for item in Kostenart._data],
            ignore_conflicts=True,
        )
        self.projekt = Projekt.create(
            ignore_permission=True,
            name="Testprojekt",
            auftragsnummer="T-2026-001",
            offerte_summe=Measurement(100_000, "CHF"),
            wv_summe=Measurement(90_000, "CHF"),
            jahr=2026,
        )
        apparate = Kostenart.filter(schluessel="apparate").first()
        assert apparate is not None
        KostenPosition.create(
            ignore_permission=True,
            projekt=self.projekt,
            art=apparate,
            offerte_kosten_wert=Measurement(30_000, "CHF"),
        )
        Stundensatz.create(
            ignore_permission=True,
            jahr=2026,
            stundensatz=Measurement(90, "CHF"),
        )


class GraphQLQueryShapeTest(_SharedSetup):
    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_superuser("tester", password="x")
        self.client.force_login(self.user)

    # ------------------------------------------------------------------
    # GET_PROJEKTE
    # ------------------------------------------------------------------

    def test_projekt_liste_shape(self) -> None:
        result = _gql(self.client, _QUERY_PROJEKT_LISTE)
        self.assertNotIn("errors", result, result.get("errors"))
        items = result["data"]["projektList"]["items"]
        self.assertEqual(len(items), 1)
        p = items[0]
        self.assertIn("id", p)
        self.assertIn("auftragsnummer", p)
        self.assertIn("offerteSumme", p)
        self.assertIn("projektKennzahlenList", p)
        kennzahlen = p["projektKennzahlenList"]["items"]
        self.assertEqual(len(kennzahlen), 1)
        self.assertIn("summeWvPlus", kennzahlen[0])
        self.assertIn("summeIstKosten", kennzahlen[0])
        self.assertIn("value", kennzahlen[0]["summeWvPlus"])

    # ------------------------------------------------------------------
    # GET_PROJEKT (Detailansicht)
    # ------------------------------------------------------------------

    def test_projekt_detail_shape(self) -> None:
        result = _gql(
            self.client,
            _QUERY_PROJEKT_DETAIL,
            variables={"id": str(self.projekt.id)},
        )
        self.assertNotIn("errors", result, result.get("errors"))
        p = result["data"]["projekt"]
        self.assertIsNotNone(p)
        self.assertEqual(p["auftragsnummer"], "T-2026-001")

        # projektKennzahlenList — Kernfelder korrekt berechnet
        kennzahlen = p["projektKennzahlenList"]["items"]
        self.assertEqual(len(kennzahlen), 1)
        kz = kennzahlen[0]
        self.assertIn("summeOfferteKosten", kz)
        self.assertIn("summeIstKosten", kz)
        self.assertEqual(kz["summeOfferteKosten"]["value"], 30000.0)
        self.assertEqual(kz["summeWvPlus"]["value"], 90000.0)

        # kostenPositionenList
        self.assertIn("kostenPositionenList", p)
        self.assertEqual(len(p["kostenPositionenList"]["items"]), 1)

        # istWertList ist vorhanden (Bexio-Fehler in Testumgebung erwartet)
        self.assertIn("istWertList", p)

    # ------------------------------------------------------------------
    # GET_FEHLENDE_STUNDENSATZ_JAHRE
    # ------------------------------------------------------------------

    def test_fehlende_stundensatz_jahre_shape(self) -> None:
        result = _gql(
            self.client,
            """
            query FehlendeStundensatzJahre {
              aufgabenStundensatz {
                fehlendeStundensatzJahre
              }
            }
            """,
        )
        self.assertNotIn("errors", result, result.get("errors"))
        # Stundensatz + Projekt 2026 in setUp → no missing years
        jahre = result["data"]["aufgabenStundensatz"]["fehlendeStundensatzJahre"]
        self.assertEqual(jahre, [])

    # ------------------------------------------------------------------
    # GET_KOSTENART_IDS
    # ------------------------------------------------------------------

    def test_kostenart_ids_shape(self) -> None:
        result = _gql(
            self.client,
            """
            query KostenartIds {
              kostenartList {
                items {
                  id
                  schluessel
                }
              }
            }
            """,
        )
        self.assertNotIn("errors", result, result.get("errors"))
        items = result["data"]["kostenartList"]["items"]
        schlussel = {i["schluessel"] for i in items}
        self.assertIn("apparate", schlussel)
        self.assertIn("regie", schlussel)
        self.assertEqual(len(items), 15)

    # ------------------------------------------------------------------
    # GET_STUNDENSAETZE
    # ------------------------------------------------------------------

    def test_stundensaetze_shape(self) -> None:
        result = _gql(
            self.client,
            """
            query StundensaetzeListe {
              stundensatzList {
                items {
                  id
                  jahr
                  stundensatz { value unit }
                }
                pageInfo { totalCount }
              }
            }
            """,
        )
        self.assertNotIn("errors", result, result.get("errors"))
        items = result["data"]["stundensatzList"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["jahr"], 2026)
        self.assertEqual(items[0]["stundensatz"]["unit"], "CHF")


# ------------------------------------------------------------------
# Berechtigungs-Tests: normaler Nutzer (kein Superuser)
# ------------------------------------------------------------------


class GraphQLPermissionTest(_SharedSetup):
    """Prüft dass reguläre Nutzer dieselben Queries ohne Fehler ausführen können."""

    def _login_as(self, username: str, groups: list[str]) -> None:
        from django.contrib.auth.models import Group

        user = User.objects.create_user(username, password="x")
        for name in groups:
            group, _ = Group.objects.get_or_create(name=name)
            user.groups.add(group)
        self.client.force_login(user)

    def test_betrachter_projekt_liste(self) -> None:
        self._login_as("simon", ["Betrachter"])
        result = _gql(self.client, _QUERY_PROJEKT_LISTE)
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertIn("projektList", result["data"])

    def test_betrachter_projekt_detail(self) -> None:
        self._login_as("simon", ["Betrachter"])
        result = _gql(
            self.client,
            _QUERY_PROJEKT_DETAIL,
            variables={"id": str(self.projekt.id)},
        )
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertIsNotNone(result["data"]["projekt"])

    def test_projektleiter_projekt_liste(self) -> None:
        self._login_as("anna", ["Projektleiter"])
        result = _gql(self.client, _QUERY_PROJEKT_LISTE)
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertIn("projektList", result["data"])

    def test_projektleiter_projekt_detail(self) -> None:
        self._login_as("anna", ["Projektleiter"])
        result = _gql(
            self.client,
            _QUERY_PROJEKT_DETAIL,
            variables={"id": str(self.projekt.id)},
        )
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertIsNotNone(result["data"]["projekt"])

    def test_ohne_gruppe_kein_zugriff_auf_projekte(self) -> None:
        self._login_as("nobody", [])
        result = _gql(self.client, _QUERY_PROJEKT_LISTE)
        # Kein Lesezugriff → leere Liste oder Fehler, aber kein Schema-Fehler
        self.assertNotIn(
            "Unknown input field",
            str(result.get("errors", "")),
            result.get("errors"),
        )
