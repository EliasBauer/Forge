"""GraphQL-Tests für den Gruppe-GM-Manager (apps.authentication.managers)."""

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


class GruppeReadTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("leser", password="x")
        self.client.force_login(self.user)
        self.group, _ = Group.objects.get_or_create(name="Betrachter")

    def test_gruppe_lesen_erlaubt(self) -> None:
        result = _gql(
            self.client,
            """
            query($id: ID!) { gruppe(id: $id) { id name } }
            """,
            {"id": str(self.group.pk)},
        )
        self.assertNotIn("errors", result, result.get("errors"))
        self.assertEqual(result["data"]["gruppe"]["name"], "Betrachter")


class GruppeWriteDeniedTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("admin5", password="x")
        group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.add(group)
        self.client.force_login(self.user)
        self.target_group, _ = Group.objects.get_or_create(name="Ziel-Gruppe")

    def test_create_ueber_graphql_verweigert(self) -> None:
        result = _gql(self.client, 'mutation { createGruppe(name: "Neu") { success } }')
        self.assertIn("errors", result)

    def test_create_ueber_python_verweigert(self) -> None:
        from apps.authentication.managers import Gruppe

        with self.assertRaises(PermissionError):
            Gruppe.create(name="Neu")

    def test_update_ueber_graphql_verweigert(self) -> None:
        gid = self.target_group.pk
        result = _gql(
            self.client,
            f'mutation {{ updateGruppe(id: {gid}, name: "Anders") {{ success }} }}',
        )
        self.assertIn("errors", result)

    def test_update_ueber_python_verweigert(self) -> None:
        from apps.authentication.managers import Gruppe

        with self.assertRaises(PermissionError):
            Gruppe(id=self.target_group.pk).update(name="Anders")

    def test_delete_ueber_graphql_verweigert(self) -> None:
        result = _gql(
            self.client,
            f"mutation {{ deleteGruppe(id: {self.target_group.pk}) {{ success }} }}",
        )
        self.assertIn("errors", result)

    def test_delete_ueber_python_verweigert(self) -> None:
        from apps.authentication.managers import Gruppe

        with self.assertRaises(PermissionError):
            Gruppe(id=self.target_group.pk).delete()
