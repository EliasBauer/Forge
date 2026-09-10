"""GraphQL-Tests für den Benutzer-GM-Manager (apps.authentication.managers)."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.models import Group, User
from django.test import TestCase

GRAPHQL_URL = "/graphql/"


def _gql(
    client: Any, query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    response = client.post(
        GRAPHQL_URL, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200, (
        f"HTTP {response.status_code}: {response.content[:500]}"
    )
    data: dict[str, Any] = response.json()
    return data


_QUERY_BENUTZER = """
    query BenutzerDetail($id: ID!) {
      benutzer(id: $id) {
        id
        username
        password
        isSuperuser
        userPermissionsList
        logEntryList
      }
    }
"""

_QUERY_BENUTZER_PERSOENLICHE_DATEN = """
    query BenutzerDetail($id: ID!) {
      benutzer(id: $id) {
        id
        username
        email
        isStaff
        firstName
        lastName
        lastLogin
        dateJoined
      }
    }
"""


class BenutzerFieldVisibilityTest(TestCase):
    def setUp(self) -> None:
        self.target = User.objects.create_user(
            username="ziel",
            password="geheim123",
            email="ziel@example.com",
            first_name="Zora",
            last_name="Ziel",
            is_staff=True,
        )

    def _login_as(self, username: str, groups: list[str]) -> None:
        user = User.objects.create_user(username, password="x")
        for name in groups:
            group, _ = Group.objects.get_or_create(name=name)
            user.groups.add(group)
        self.client.force_login(user)

    def test_password_ist_fuer_betrachter_null(self) -> None:
        self._login_as("betrachter1", ["Betrachter"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertIsNone(result["data"]["benutzer"]["password"])

    def test_password_ist_auch_fuer_admin_null(self) -> None:
        self._login_as("admin1", ["Admin"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertIsNone(result["data"]["benutzer"]["password"])

    def test_is_superuser_nur_fuer_admin_sichtbar(self) -> None:
        self._login_as("admin2", ["Admin"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertIsNotNone(result["data"]["benutzer"]["isSuperuser"])
        self.assertIsNotNone(result["data"]["benutzer"]["userPermissionsList"])
        self.assertIsNotNone(result["data"]["benutzer"]["logEntryList"])

    def test_is_superuser_fuer_betrachter_null(self) -> None:
        self._login_as("betrachter2", ["Betrachter"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertIsNone(result["data"]["benutzer"]["isSuperuser"])
        self.assertIsNone(result["data"]["benutzer"]["userPermissionsList"])
        self.assertIsNone(result["data"]["benutzer"]["logEntryList"])

    def test_persoenliche_daten_nur_fuer_admin_sichtbar(self) -> None:
        self._login_as("admin5", ["Admin"])
        result = _gql(
            self.client,
            _QUERY_BENUTZER_PERSOENLICHE_DATEN,
            {"id": str(self.target.pk)},
        )
        self.assertNotIn("errors", result, result.get("errors"))
        benutzer = result["data"]["benutzer"]
        self.assertEqual(benutzer["email"], "ziel@example.com")
        self.assertTrue(benutzer["isStaff"])
        self.assertEqual(benutzer["firstName"], "Zora")
        self.assertEqual(benutzer["lastName"], "Ziel")
        self.assertIsNotNone(benutzer["dateJoined"])

    def test_persoenliche_daten_fuer_betrachter_null(self) -> None:
        self._login_as("betrachter4", ["Betrachter"])
        result = _gql(
            self.client,
            _QUERY_BENUTZER_PERSOENLICHE_DATEN,
            {"id": str(self.target.pk)},
        )
        self.assertNotIn("errors", result, result.get("errors"))
        benutzer = result["data"]["benutzer"]
        self.assertIsNone(benutzer["email"])
        self.assertIsNone(benutzer["isStaff"])
        self.assertIsNone(benutzer["firstName"])
        self.assertIsNone(benutzer["lastName"])
        self.assertIsNone(benutzer["lastLogin"])
        self.assertIsNone(benutzer["dateJoined"])
        # username bleibt für jeden Eingeloggten sichtbar (unveränderte
        # Basis-Sichtbarkeit, nur die persönlichen Daten werden gegated).
        self.assertEqual(benutzer["username"], "ziel")

    def test_username_ist_fuer_eingeloggte_sichtbar(self) -> None:
        self._login_as("betrachter3", ["Betrachter"])
        result = _gql(self.client, _QUERY_BENUTZER, {"id": str(self.target.pk)})
        self.assertEqual(result["data"]["benutzer"]["username"], "ziel")

    def test_benutzerlist_gefiltert_nach_gruppe(self) -> None:
        self._login_as("admin3", ["Admin"])
        pl = User.objects.create_user("pl_test", password="x")
        group, _ = Group.objects.get_or_create(name="Projektleiter")
        pl.groups.add(group)
        result = _gql(
            self.client,
            """
            query {
              benutzerList(filter: { groupsList: { any: { name: "Projektleiter" } } }) {
                items { id username }
              }
            }
            """,
        )
        self.assertNotIn("errors", result, result.get("errors"))
        usernames = [u["username"] for u in result["data"]["benutzerList"]["items"]]
        self.assertEqual(usernames, ["pl_test"])


class BenutzerWriteDeniedTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("admin4", password="x")
        group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.add(group)
        self.client.force_login(self.user)

    def test_create_ueber_graphql_verweigert(self) -> None:
        result = _gql(
            self.client, 'mutation { createBenutzer(username: "x") { success } }'
        )
        self.assertIn("errors", result)

    def test_create_ueber_python_verweigert(self) -> None:
        from apps.authentication.managers import Benutzer

        with self.assertRaises(PermissionError):
            Benutzer.create(username="x")


class HistoryRegistrationGuardTest(TestCase):
    def test_bereits_registriertes_model_wird_uebersprungen(self) -> None:
        """Der hasattr-Guard verhindert doppelte simple_history-Registrierung
        bei einem erneuten Aufruf (z. B. Modul-Reimport durch Autoreload)."""
        from apps.authentication.managers import _register_history_if_needed

        self.assertTrue(hasattr(User._meta, "simple_history_manager_attribute"))
        _register_history_if_needed(User)  # darf nicht erneut register() aufrufen
