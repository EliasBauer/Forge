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

    def test_create_ueber_graphql_verweigert(self) -> None:
        result = _gql(self.client, 'mutation { createGruppe(name: "Neu") { success } }')
        self.assertIn("errors", result)
