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


class UsersViewTest(TestCase):
    def setUp(self) -> None:
        from django.contrib.auth.models import Group

        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.projektleiter = User.objects.create_user(
            username="pl_user", password="testpass123"
        )
        group, _ = Group.objects.get_or_create(name="Projektleiter")
        self.projektleiter.groups.add(group)
        self.url = reverse("auth-users")

    def test_returns_only_projektleiter_when_authenticated(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()]
        self.assertIn("pl_user", usernames)
        self.assertNotIn("testuser", usernames)

    def test_returns_401_when_unauthenticated(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)


class CurrentUserViewTest(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.url = reverse("auth-me")

    def test_returns_user_when_authenticated(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "testuser")

    def test_returns_null_when_unauthenticated(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json())
