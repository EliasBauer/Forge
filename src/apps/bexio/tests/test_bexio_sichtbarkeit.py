"""Rollenabhängige Sichtbarkeit der bexio-Rohdaten.

Warum dieser Test existiert: Die Projektdetailseite verwehrt Monteuren die
Ist-Kosten, und `IstWert`/`ProjektKennzahlen` setzen das serverseitig durch.
Beide berechnen ihren Wert aber aus `Lieferantenrechnung` als
`sum(betrag - steuer_berechnet)` je `richtiger_titel`, und `richtiger_titel`
ist die `auftragsnummer` eines Projekts — die ein Monteur sehen darf.

Solange `Lieferantenrechnung` auf `isAuthenticated` stand, war die Absicherung
der abgeleiteten Werte damit wertlos: ein Monteur konnte das Journal direkt
abfragen und die Ist-Kosten je Projekt selbst zusammenrechnen. Für einen
Betrachter war es sogar mehr, als ihm auf der Detailseite verwehrt wird — das
komplette Journal über alle Projekte und Lieferanten, ganz ohne Join.

Diese Tests halten fest, dass die Rohdaten mindestens so eng sind wie das,
was aus ihnen berechnet wird.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import Group, User
from django.test import TestCase

from apps.bexio.models import Konto, Lieferantenrechnung

_LieferantenrechnungModel: Any = Lieferantenrechnung.Interface._model  # type: ignore[misc]
_KontoModel: Any = Konto.Interface._model  # type: ignore[misc]

LIEFERANTENRECHNUNG_QUERY = """
query {
  lieferantenrechnungList {
    items { richtigerTitel firmenname betrag steuerBerechnet }
    pageInfo { totalCount }
  }
}
"""

KONTO_QUERY = """
query {
  kontoList {
    items { accountNo name }
    pageInfo { totalCount }
  }
}
"""


class BexioRohdatenSichtbarkeitTest(TestCase):
    def setUp(self) -> None:
        _KontoModel.objects.create(
            bexio_id=uuid.uuid4(),
            bexio_int_id=4000,
            account_no="4000",
            name="Materialaufwand",
        )
        _LieferantenrechnungModel.objects.create(
            bexio_id=uuid.uuid4(),
            bexio_zeilen_id=uuid.uuid4(),
            dokument_nr="2024-R-001",
            titel="Rechnung",
            richtiger_titel="2024-900",
            status="paid",
            rechnungsdatum=date(2024, 1, 15),
            lieferant_id=1,
            firmenname="Lieferant AG",
            waehrung_code="CHF",
            rechnungsbetrag=Decimal("12345.67"),
            ausstehender_betrag=Decimal("0.00"),
            bexio_erstellt_am=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            betrag=Decimal("12000.00"),
            steuer_berechnet=Decimal("345.67"),
        )

    def _login(self, gruppe: str) -> None:
        user = User.objects.create_user(f"u_{gruppe.lower()}", password="x")
        group, _ = Group.objects.get_or_create(name=gruppe)
        user.groups.add(group)
        self.client.force_login(user)

    def _anzahl(self, query: str, wurzel: str) -> int:
        response = self.client.post(
            "/graphql/",
            data=json.dumps({"query": query}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        return int(payload["data"][wurzel]["pageInfo"]["totalCount"])

    def _rechnungen(self) -> int:
        return self._anzahl(LIEFERANTENRECHNUNG_QUERY, "lieferantenrechnungList")

    def _konten(self) -> int:
        return self._anzahl(KONTO_QUERY, "kontoList")

    # ---------------- verwehrt ----------------

    def test_anonym_sieht_keine_lieferantenrechnungen(self) -> None:
        self.assertEqual(self._rechnungen(), 0)

    def test_anonym_sieht_keine_konten(self) -> None:
        self.assertEqual(self._konten(), 0)

    def test_monteur_sieht_keine_lieferantenrechnungen(self) -> None:
        self._login("Monteur")
        self.assertEqual(self._rechnungen(), 0)

    def test_monteur_sieht_keine_konten(self) -> None:
        self._login("Monteur")
        self.assertEqual(self._konten(), 0)

    # ---------------- erlaubt ----------------

    def test_betrachter_sieht_lieferantenrechnungen(self) -> None:
        self._login("Betrachter")
        self.assertEqual(self._rechnungen(), 1)

    def test_projektleiter_sieht_lieferantenrechnungen(self) -> None:
        self._login("Projektleiter")
        self.assertEqual(self._rechnungen(), 1)

    def test_admin_sieht_lieferantenrechnungen(self) -> None:
        self._login("Admin")
        self.assertEqual(self._rechnungen(), 1)

    def test_projektleiter_sieht_konten(self) -> None:
        self._login("Projektleiter")
        self.assertEqual(self._konten(), 1)
