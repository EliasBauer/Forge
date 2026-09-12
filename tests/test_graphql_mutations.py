"""
Integrationstests: GraphQL-Mutations aus frontend/src/graphql/mutations.ts

Jeder Test sendet die exakte Mutation ans /graphql/-Endpoint und prüft:
- HTTP 200
- Keine GraphQL-Fehler in der Antwort
- success == True

Ziel: Schema-Drift frühzeitig erkennen, bevor er zur Laufzeit auffällt (siehe
test_graphql_queries.py für den Query-Gegenpart). Query-Strings sind bewusst
1:1 aus mutations.ts übernommen — bei Änderungen dort bitte hier mitziehen.
"""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.models import User
from django.test import TestCase
from general_manager.measurement import Measurement

from apps.projekt.models import Kostenart, KostenPosition, Projekt
from apps.projekt.models.projekt_status import ProjektStatus
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


_MUTATION_CREATE_PROJEKT = """
    mutation CreateProjekt(
      $name: String!
      $auftragsnummer: String!
      $jahr: Int!
      $offerteSumme: MeasurementScalar!
      $wvSumme: MeasurementScalar
      $projektleiter: ID
      $projektStatus: ID!
    ) {
      createProjekt(
        name: $name
        auftragsnummer: $auftragsnummer
        jahr: $jahr
        offerteSumme: $offerteSumme
        wvSumme: $wvSumme
        projektleiter: $projektleiter
        projektStatus: $projektStatus
      ) {
        success
        Projekt { id }
      }
    }
"""

_MUTATION_UPDATE_PROJEKT = """
    mutation UpdateProjekt(
      $id: Int!
      $name: String
      $offerteSumme: MeasurementScalar
      $wvSumme: MeasurementScalar
      $projektleiter: ID
      $projektStatus: ID
    ) {
      updateProjekt(
        id: $id
        name: $name
        offerteSumme: $offerteSumme
        wvSumme: $wvSumme
        projektleiter: $projektleiter
        projektStatus: $projektStatus
      ) {
        success
      }
    }
"""

_MUTATION_CREATE_KOSTEN_POSITION = """
    mutation CreateKostenPosition(
      $projekt: ID!
      $art: ID!
      $offerteKostenWert: MeasurementScalar
    ) {
      createKostenPosition(
        projekt: $projekt
        art: $art
        offerteKostenWert: $offerteKostenWert
      ) {
        success
      }
    }
"""

_MUTATION_UPDATE_KOSTEN_POSITION = """
    mutation UpdateKostenPosition($id: Int!, $offerteKostenWert: MeasurementScalar) {
      updateKostenPosition(id: $id, offerteKostenWert: $offerteKostenWert) {
        success
      }
    }
"""

_MUTATION_DELETE_KOSTEN_POSITION = """
    mutation DeleteKostenPosition($id: Int!) {
      deleteKostenPosition(id: $id) {
        success
      }
    }
"""

_MUTATION_CREATE_STUNDENSATZ = """
    mutation CreateStundensatz($jahr: Int!, $stundensatz: MeasurementScalar!) {
      createStundensatz(jahr: $jahr, stundensatz: $stundensatz) {
        success
        Stundensatz { id }
      }
    }
"""

_MUTATION_UPDATE_STUNDENSATZ = """
    mutation UpdateStundensatz($id: Int!, $stundensatz: MeasurementScalar!) {
      updateStundensatz(id: $id, stundensatz: $stundensatz) {
        success
      }
    }
"""

_MUTATION_DELETE_STUNDENSATZ = """
    mutation DeleteStundensatz($id: Int!) {
      deleteStundensatz(id: $id) {
        success
      }
    }
"""


class GraphQLMutationShapeTest(TestCase):
    def setUp(self) -> None:
        _KostenartModel.objects.bulk_create(
            [_KostenartModel(**item) for item in Kostenart._data],
            ignore_conflicts=True,
        )
        self.user = User.objects.create_superuser("mut_tester", password="x")
        self.client.force_login(self.user)
        self.projektleiter = User.objects.create_user("mut_pl", password="x")

    # ------------------------------------------------------------------
    # CREATE_PROJEKT / UPDATE_PROJEKT
    # ------------------------------------------------------------------

    def test_create_projekt(self) -> None:
        offen = ProjektStatus.filter(name="Offen").first()
        assert offen is not None
        result = _gql(
            self.client,
            _MUTATION_CREATE_PROJEKT,
            variables={
                "name": "Mutationstest",
                "auftragsnummer": "MUT-001",
                "jahr": 2026,
                "offerteSumme": "10000 CHF",
                "wvSumme": "9000 CHF",
                "projektleiter": str(self.projektleiter.id),
                "projektStatus": str(offen.id),
            },
        )
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertTrue(result["data"]["createProjekt"]["success"])
        self.assertIsNotNone(result["data"]["createProjekt"]["Projekt"]["id"])

    def test_update_projekt(self) -> None:
        projekt = Projekt.create(
            ignore_permission=True,
            projekt_status=ProjektStatus.filter(name="Offen").first(),
            name="Vor Update",
            auftragsnummer="MUT-002",
            offerte_summe=Measurement(10_000, "CHF"),
            wv_summe=Measurement(9_000, "CHF"),
            jahr=2026,
        )
        status = ProjektStatus.filter(name="In Arbeit").first()
        assert status is not None
        result = _gql(
            self.client,
            _MUTATION_UPDATE_PROJEKT,
            variables={
                "id": projekt.id,
                "name": "Nach Update",
                "projektleiter": str(self.projektleiter.id),
                "projektStatus": str(status.id),
            },
        )
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertTrue(result["data"]["updateProjekt"]["success"])

    # ------------------------------------------------------------------
    # KOSTEN_POSITION-Mutations
    # ------------------------------------------------------------------

    def test_create_update_delete_kosten_position(self) -> None:
        projekt = Projekt.create(
            ignore_permission=True,
            projekt_status=ProjektStatus.filter(name="Offen").first(),
            name="KP-Test",
            auftragsnummer="MUT-003",
            offerte_summe=Measurement(10_000, "CHF"),
            wv_summe=Measurement(9_000, "CHF"),
            jahr=2026,
        )
        art = Kostenart.filter(schluessel="apparate").first()
        assert art is not None

        created = _gql(
            self.client,
            _MUTATION_CREATE_KOSTEN_POSITION,
            variables={
                "projekt": str(projekt.id),
                "art": str(art.id),
                "offerteKostenWert": "5000 CHF",
            },
        )
        self.assertNotIn("errors", created, created.get("errors"))
        self.assertTrue(created["data"]["createKostenPosition"]["success"])

        position = KostenPosition.filter(projekt=projekt).first()
        assert position is not None

        updated = _gql(
            self.client,
            _MUTATION_UPDATE_KOSTEN_POSITION,
            variables={"id": position.id, "offerteKostenWert": "6000 CHF"},
        )
        self.assertNotIn("errors", updated, updated.get("errors"))
        self.assertTrue(updated["data"]["updateKostenPosition"]["success"])

        deleted = _gql(
            self.client,
            _MUTATION_DELETE_KOSTEN_POSITION,
            variables={"id": position.id},
        )
        self.assertNotIn("errors", deleted, deleted.get("errors"))
        self.assertTrue(deleted["data"]["deleteKostenPosition"]["success"])

    # ------------------------------------------------------------------
    # STUNDENSATZ-Mutations
    # ------------------------------------------------------------------

    def test_create_update_delete_stundensatz(self) -> None:
        created = _gql(
            self.client,
            _MUTATION_CREATE_STUNDENSATZ,
            variables={"jahr": 2027, "stundensatz": "95 CHF"},
        )
        self.assertNotIn("errors", created, created.get("errors"))
        self.assertTrue(created["data"]["createStundensatz"]["success"])

        stundensatz = Stundensatz.filter(jahr=2027).first()
        assert stundensatz is not None

        updated = _gql(
            self.client,
            _MUTATION_UPDATE_STUNDENSATZ,
            variables={"id": stundensatz.id, "stundensatz": "100 CHF"},
        )
        self.assertNotIn("errors", updated, updated.get("errors"))
        self.assertTrue(updated["data"]["updateStundensatz"]["success"])

        deleted = _gql(
            self.client,
            _MUTATION_DELETE_STUNDENSATZ,
            variables={"id": stundensatz.id},
        )
        self.assertNotIn("errors", deleted, deleted.get("errors"))
        self.assertTrue(deleted["data"]["deleteStundensatz"]["success"])
