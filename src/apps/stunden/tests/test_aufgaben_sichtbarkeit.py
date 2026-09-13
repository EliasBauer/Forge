"""Rollenabhängige Sichtbarkeit der Aufgaben-Auswertung.

`AufgabenStundensatz` war lange der einzige Manager ohne eigenes `__read__` und
erbte damit den Settings-Default. Der stand früher auf `public` — die Abfrage
war also anonym lesbar, obwohl CONTEXT.md „kein anonymer Zugriff" festlegt.
Nach der Verschärfung des Defaults auf `isAdmin` (= `user.is_staff`) kippte es
ins andere Extrem: selbst Mitglieder der Gruppe „Admin" bekamen nichts mehr,
weil `isAdmin` die Gruppe gar nicht prüft. Aufgefallen wäre das lokal nicht,
weil der Dev-Admin zusätzlich `is_staff=True` und `is_superuser=True` hat.

Diese Tests halten beide Enden fest: nicht anonym lesbar, aber für die Rollen
lesbar, die Stundensätze auch pflegen dürfen.
"""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.models import Group, User
from django.test import TestCase

AUFGABEN_QUERY = """
query { aufgabenStundensatz { fehlendeStundensatzJahre } }
"""


class AufgabenStundensatzSichtbarkeitTest(TestCase):
    def _login(self, gruppe: str) -> None:
        user = User.objects.create_user(f"u_{gruppe.lower()}", password="x")
        group, _ = Group.objects.get_or_create(name=gruppe)
        user.groups.add(group)
        self.client.force_login(user)

    def _jahre(self) -> Any:
        response = self.client.post(
            "/graphql/",
            data=json.dumps({"query": AUFGABEN_QUERY}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        return payload["data"]["aufgabenStundensatz"]["fehlendeStundensatzJahre"]

    def test_anonym_bekommt_keine_auswertung(self) -> None:
        self.assertIsNone(self._jahre())

    def test_monteur_bekommt_keine_auswertung(self) -> None:
        self._login("Monteur")
        self.assertIsNone(self._jahre())

    def test_betrachter_bekommt_keine_auswertung(self) -> None:
        self._login("Betrachter")
        self.assertIsNone(self._jahre())

    def test_projektleiter_bekommt_die_auswertung(self) -> None:
        self._login("Projektleiter")
        self.assertIsInstance(self._jahre(), list)

    def test_admin_gruppe_bekommt_die_auswertung(self) -> None:
        """Gruppe „Admin" ohne is_staff — prüft isForgeAdmin, nicht isAdmin."""
        self._login("Admin")
        self.assertIsInstance(self._jahre(), list)
