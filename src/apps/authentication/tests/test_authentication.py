"""Tests für die Permission-Funktionen und Authentication-Views."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from apps.authentication.permission import (
    _permission_is_admin,
    _permission_is_mechanic,
    _permission_is_project_leader,
    _permission_is_viewer,
    _permission_never,
)


def _make_user(group: str | None) -> MagicMock:
    user = MagicMock()

    def mock_filter(**kwargs: str) -> MagicMock:
        qs = MagicMock()
        qs.exists.return_value = kwargs.get("name") == group
        return qs

    user.groups.filter.side_effect = mock_filter
    return user


class IsInGroupTest(TestCase):
    def test_returns_false_when_groups_is_none(self) -> None:
        from apps.authentication.permission import _is_in_group

        user = MagicMock(spec=[])  # no attributes → getattr returns None
        self.assertFalse(_is_in_group(user, "Admin"))


class PermissionIsAdminTest(TestCase):
    def test_returns_true_for_admin(self) -> None:
        self.assertTrue(_permission_is_admin(MagicMock(), _make_user("Admin"), []))

    def test_returns_false_for_other_group(self) -> None:
        self.assertFalse(_permission_is_admin(MagicMock(), _make_user("Monteur"), []))

    def test_returns_false_for_no_group(self) -> None:
        self.assertFalse(_permission_is_admin(MagicMock(), _make_user(None), []))


class PermissionIsProjektleiterTest(TestCase):
    def test_returns_true_for_projektleiter(self) -> None:
        self.assertTrue(
            _permission_is_project_leader(MagicMock(), _make_user("Projektleiter"), [])
        )

    def test_returns_false_for_other_group(self) -> None:
        self.assertFalse(
            _permission_is_project_leader(MagicMock(), _make_user("Admin"), [])
        )

    def test_returns_false_for_no_group(self) -> None:
        self.assertFalse(
            _permission_is_project_leader(MagicMock(), _make_user(None), [])
        )


class PermissionIsBetrachterTest(TestCase):
    def test_returns_true_for_betrachter(self) -> None:
        self.assertTrue(
            _permission_is_viewer(MagicMock(), _make_user("Betrachter"), [])
        )

    def test_returns_false_for_other_group(self) -> None:
        self.assertFalse(_permission_is_viewer(MagicMock(), _make_user("Admin"), []))

    def test_returns_false_for_no_group(self) -> None:
        self.assertFalse(_permission_is_viewer(MagicMock(), _make_user(None), []))


class PermissionIsMonteurTest(TestCase):
    def test_returns_true_for_monteur(self) -> None:
        self.assertTrue(_permission_is_mechanic(MagicMock(), _make_user("Monteur"), []))

    def test_returns_false_for_other_group(self) -> None:
        self.assertFalse(_permission_is_mechanic(MagicMock(), _make_user("Admin"), []))

    def test_returns_false_for_no_group(self) -> None:
        self.assertFalse(_permission_is_mechanic(MagicMock(), _make_user(None), []))


class PermissionNeverTest(TestCase):
    def test_returns_false_immer(self) -> None:
        self.assertFalse(_permission_never(MagicMock(), _make_user("Admin"), []))
        self.assertFalse(_permission_never(MagicMock(), _make_user(None), []))


class LoginViewTest(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.url = reverse("auth-login")

    def test_login_success(self) -> None:
        response = self.client.post(
            self.url,
            data=json.dumps({"username": "testuser", "password": "testpass123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_login_invalid_credentials(self) -> None:
        response = self.client.post(
            self.url,
            data=json.dumps({"username": "testuser", "password": "wrong"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_login_invalid_json(self) -> None:
        response = self.client.post(
            self.url,
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])


class LogoutViewTest(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.url = reverse("auth-logout")

    def test_logout(self) -> None:
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])


class RemovedRestEndpointsTest(TestCase):
    def test_users_endpoint_existiert_nicht_mehr(self) -> None:
        from django.urls import NoReverseMatch, reverse

        with self.assertRaises(NoReverseMatch):
            reverse("auth-users")

    def test_me_endpoint_existiert_nicht_mehr(self) -> None:
        from django.urls import NoReverseMatch, reverse

        with self.assertRaises(NoReverseMatch):
            reverse("auth-me")


class CurrentUserCapabilitiesTest(TestCase):
    def _gql(self) -> dict[str, object]:
        import json

        response = self.client.post(
            "/graphql/",
            data=json.dumps(
                {
                    "query": """
                    query {
                      me {
                        username
                        capabilities {
                          canCreateProjekt
                          canManageStundensaetze
                          canViewFinanzen
                        }
                      }
                    }
                    """
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()  # type: ignore[no-any-return]

    def test_anonymous_alle_capabilities_false(self) -> None:
        result = self._gql()
        self.assertEqual(result["data"]["me"]["username"], "")  # type: ignore[index]
        caps = result["data"]["me"]["capabilities"]  # type: ignore[index]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": False,
                "canManageStundensaetze": False,
                "canViewFinanzen": False,
            },
        )

    def test_admin_alle_capabilities_true(self) -> None:
        from django.contrib.auth.models import Group

        user = User.objects.create_user("admincaps", password="x")
        group, _ = Group.objects.get_or_create(name="Admin")
        user.groups.add(group)
        self.client.force_login(user)
        result = self._gql()
        self.assertEqual(result["data"]["me"]["username"], "admincaps")  # type: ignore[index]
        caps = result["data"]["me"]["capabilities"]  # type: ignore[index]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": True,
                "canManageStundensaetze": True,
                "canViewFinanzen": True,
            },
        )

    def test_monteur_darf_nur_nichts(self) -> None:
        from django.contrib.auth.models import Group

        user = User.objects.create_user("monteurcaps", password="x")
        group, _ = Group.objects.get_or_create(name="Monteur")
        user.groups.add(group)
        self.client.force_login(user)
        caps = self._gql()["data"]["me"]["capabilities"]  # type: ignore[index]
        self.assertEqual(
            caps,
            {
                "canCreateProjekt": False,
                "canManageStundensaetze": False,
                "canViewFinanzen": False,
            },
        )
