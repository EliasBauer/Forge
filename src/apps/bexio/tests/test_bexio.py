"""Tests für die Bexio-App: sync, services, tasks, admin."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.bexio.models import Konto, Lieferantenrechnung
from apps.bexio.sync import (
    compute_correct_title,
    full_sync_konten,
    full_sync_lieferantenrechnungen,
    sync_konten,
    sync_lieferantenrechnungen,
)

_LieferantenrechnungModel: Any = Lieferantenrechnung.Interface._model  # type: ignore[misc]
_KontoModel: Any = Konto.Interface._model  # type: ignore[misc]

# Dev-Fixture hat 29 Bills mit insgesamt 40 Zeilenpositionen
_EXPECTED_ROW_COUNT = 40
# Dev-Fixture für Konten hat 7 Einträge
_EXPECTED_KONTO_COUNT = 7

# ---------------------------------------------------------------------------
# compute_correct_title — reine Logik, kein DB
# ---------------------------------------------------------------------------


def test_correct_title_normal() -> None:
    assert compute_correct_title("2025.0404", "01558") == "2025.0404"


def test_correct_title_900_prefix_uses_document_no() -> None:
    assert compute_correct_title("900.2025.0198", "01480") == "01480"


def test_correct_title_9001_is_not_900_error() -> None:
    assert compute_correct_title("9001.something", "99999") == "9001.something"


def test_correct_title_empty_string() -> None:
    assert compute_correct_title("", "01234") == ""


# ---------------------------------------------------------------------------
# Sync-Funktion (mit DEV-Fixture)
# ---------------------------------------------------------------------------


@override_settings(BEXIO_DEV_MODE=True)
class SyncLieferantenrechnungenTest(TestCase):
    """Nutzt BEXIO_DEV_MODE=True — kein echter API-Zugriff."""

    def test_sync_creates_rows_per_line_item(self) -> None:
        count = sync_lieferantenrechnungen()
        assert count == _EXPECTED_ROW_COUNT
        assert _LieferantenrechnungModel.objects.count() == _EXPECTED_ROW_COUNT

    def test_bill_with_two_line_items_creates_two_rows(self) -> None:
        sync_lieferantenrechnungen()
        # Bill a1b2c3d4 hat 2 line_items
        import uuid

        rows = _LieferantenrechnungModel.objects.filter(
            bexio_id=uuid.UUID("a1b2c3d4-0001-0001-0001-000000000001")
        )
        assert rows.count() == 2

    def test_sync_is_idempotent(self) -> None:
        sync_lieferantenrechnungen()
        sync_lieferantenrechnungen()
        assert _LieferantenrechnungModel.objects.count() == _EXPECTED_ROW_COUNT

    def test_correct_title_900_prefix_stored(self) -> None:
        sync_lieferantenrechnungen()
        rechnung = _LieferantenrechnungModel.objects.get(titel="900.2025.0198")
        assert rechnung.richtiger_titel == rechnung.dokument_nr

    def test_correct_title_normal_stored(self) -> None:
        sync_lieferantenrechnungen()
        # Bill 01558 hat titel="2026.0008" → kein 900.-Prefix → richtiger_titel == titel
        rechnung = _LieferantenrechnungModel.objects.get(dokument_nr="01558")
        assert rechnung.richtiger_titel == "2026.0008"

    def test_decimal_rechnungsbetrag(self) -> None:
        sync_lieferantenrechnungen()
        rechnung = _LieferantenrechnungModel.objects.get(dokument_nr="01558")
        assert rechnung.rechnungsbetrag == Decimal("2309.10")

    def test_zeilen_betrag_und_steuer(self) -> None:
        sync_lieferantenrechnungen()
        rechnung = _LieferantenrechnungModel.objects.get(dokument_nr="01558")
        assert rechnung.betrag == Decimal("2309.10")
        assert rechnung.steuer_berechnet == Decimal("173.02")

    def test_netto_betrag_berechnung(self) -> None:
        sync_lieferantenrechnungen()
        rechnung = Lieferantenrechnung.filter(dokument_nr="01558").first()
        assert rechnung is not None
        assert rechnung.netto_betrag == Decimal("2136.08")

    def test_upsert_overwrites_changed_values(self) -> None:
        sync_lieferantenrechnungen()
        Model = _LieferantenrechnungModel
        Model.objects.filter(dokument_nr="01558").update(status="MANUALLY_CHANGED")
        sync_lieferantenrechnungen()
        assert Model.objects.get(dokument_nr="01558").status == "BOOKED"

    def test_sync_accepts_bills_without_title(self) -> None:
        """405 von 1760 echten Bexio-Belegen haben title=None (kein Projektbezug)."""
        from apps.bexio.services import _DEV_FIXTURE

        bill = {**_DEV_FIXTURE[0], "title": None}
        with patch("apps.bexio.sync.BexioClient") as MockClient:
            MockClient.return_value.get_all_bills.return_value = [bill]
            count = sync_lieferantenrechnungen()

        assert count == len(bill["line_items"])
        row = Lieferantenrechnung.all().first()
        assert row is not None
        assert row.titel == ""
        assert row.richtiger_titel == ""

    def test_sync_returns_zero_for_empty_response(self) -> None:
        with patch("apps.bexio.sync.BexioClient") as MockClient:
            MockClient.return_value.get_all_bills.return_value = []
            count = sync_lieferantenrechnungen()
        assert count == 0

    def test_full_sync_deletes_and_recreates(self) -> None:
        sync_lieferantenrechnungen()
        count = full_sync_lieferantenrechnungen()
        assert count == _EXPECTED_ROW_COUNT
        assert _LieferantenrechnungModel.objects.count() == _EXPECTED_ROW_COUNT

    def test_sync_deletes_rows_bexio_no_longer_delivers(self) -> None:
        sync_lieferantenrechnungen()
        from apps.bexio.services import BexioClient

        erste_bill = BexioClient().get_all_bills()[:1]
        erwartete_zeilen = len(erste_bill[0]["line_items"])
        with patch("apps.bexio.sync.BexioClient") as MockClient:
            MockClient.return_value.get_all_bills.return_value = erste_bill
            sync_lieferantenrechnungen()
        assert _LieferantenrechnungModel.objects.count() == erwartete_zeilen

    def test_sync_keeps_rows_when_bexio_returns_nothing(self) -> None:
        sync_lieferantenrechnungen()
        with patch("apps.bexio.sync.BexioClient") as MockClient:
            MockClient.return_value.get_all_bills.return_value = []
            sync_lieferantenrechnungen()
        assert _LieferantenrechnungModel.objects.count() == _EXPECTED_ROW_COUNT


# ---------------------------------------------------------------------------
# BexioClient — Service-Klasse
# ---------------------------------------------------------------------------


@override_settings(BEXIO_DEV_MODE=True)
class BexioClientDevModeTest(TestCase):
    def test_dev_mode_returns_fixture(self) -> None:
        from apps.bexio.services import _DEV_FIXTURE, BexioClient

        client = BexioClient()
        assert client.get_all_bills() == _DEV_FIXTURE


@override_settings(BEXIO_DEV_MODE=False, BEXIO_ACCESS_TOKEN="test-token")
class BexioClientRealApiTest(TestCase):
    def _make_response(self, data: Any, status_code: int = 200) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = data
        resp.raise_for_status = MagicMock()
        return resp

    def _make_page(self, bills: list[dict[str, Any]], page_count: int) -> MagicMock:
        return self._make_response(
            {"data": bills, "paging": {"page_count": page_count}}
        )

    def test_headers_contain_bearer_token(self) -> None:
        from apps.bexio.services import BexioClient

        client = BexioClient()
        assert client._headers["Authorization"] == "Bearer test-token"
        assert client._headers["Accept"] == "application/json"

    def _route(self, pages: list[MagicMock]) -> Any:
        """Listenaufrufe liefern die Seiten der Reihe nach, Detailaufrufe den Beleg.

        Die Liste von /4.0/purchase/bills ist eine Kurzfassung ohne supplier_id
        und line_items; erst /4.0/purchase/bills/{id} liefert die Felder, die
        die Synchronisation braucht.
        """
        remaining = iter(pages)

        def side_effect(url: str, **_: Any) -> MagicMock:
            if url.endswith("/purchase/bills"):
                return next(remaining)
            bill_id = url.rsplit("/", 1)[1]
            return self._make_response(
                {"id": bill_id, "supplier_id": 144, "line_items": []}
            )

        return side_effect

    def test_get_all_bills_sends_page_and_limit(self) -> None:
        """Der 4.0-Endpoint kennt page/limit; offset wird stillschweigend ignoriert."""
        from apps.bexio.services import _PAGE_SIZE, BexioClient

        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.side_effect = self._route(
                [self._make_page([{"id": "abc"}], page_count=1)]
            )
            BexioClient().get_all_bills()

        list_call = mock_get.call_args_list[0]
        assert list_call.kwargs["params"] == {"page": 1, "limit": _PAGE_SIZE}

    def test_get_all_bills_returns_details_not_list_summaries(self) -> None:
        from apps.bexio.services import BEXIO_API_BASE, BexioClient

        summaries = [{"id": "id-0", "vendor": "x"}, {"id": "id-1", "vendor": "y"}]
        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.side_effect = self._route([self._make_page(summaries, 1)])
            result = BexioClient().get_all_bills()

        assert [b["id"] for b in result] == ["id-0", "id-1"]
        assert all(b["supplier_id"] == 144 for b in result)
        assert all("line_items" in b for b in result)
        urls = [c.args[0] for c in mock_get.call_args_list]
        assert urls == [
            f"{BEXIO_API_BASE}/4.0/purchase/bills",
            f"{BEXIO_API_BASE}/4.0/purchase/bills/id-0",
            f"{BEXIO_API_BASE}/4.0/purchase/bills/id-1",
        ]

    def test_get_all_bills_empty(self) -> None:
        from apps.bexio.services import BexioClient

        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.side_effect = self._route([self._make_page([], page_count=0)])
            result = BexioClient().get_all_bills()

        assert result == []
        assert mock_get.call_count == 1

    def test_get_all_bills_paginates_until_page_count(self) -> None:
        """Abbruch über paging.page_count, nicht über eine "kurze" letzte Seite."""
        from apps.bexio.services import BexioClient

        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.side_effect = self._route(
                [
                    self._make_page([{"id": "a"}, {"id": "b"}], page_count=3),
                    self._make_page([{"id": "c"}, {"id": "d"}], page_count=3),
                    self._make_page([{"id": "e"}], page_count=3),
                ]
            )
            result = BexioClient().get_all_bills()

        assert [b["id"] for b in result] == ["a", "b", "c", "d", "e"]
        pages = [
            c.kwargs["params"]["page"]
            for c in mock_get.call_args_list
            if c.args[0].endswith("/purchase/bills")
        ]
        assert pages == [1, 2, 3]

    def test_get_bill_raises_on_unexpected_detail(self) -> None:
        from apps.bexio.services import BexioClient

        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.side_effect = [
                self._make_page([{"id": "abc"}], page_count=1),
                self._make_response({"data": []}),
            ]
            with self.assertRaisesMessage(RuntimeError, "Unerwartetes Antwortformat"):
                BexioClient().get_all_bills()

    def test_get_all_bills_raises_on_unexpected_format(self) -> None:
        from apps.bexio.services import BexioClient

        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.return_value = self._make_response([{"id": "abc"}])
            with self.assertRaisesMessage(RuntimeError, "Unerwartetes Antwortformat"):
                BexioClient().get_all_bills()


# ---------------------------------------------------------------------------
# Celery Task
# ---------------------------------------------------------------------------


@override_settings(BEXIO_DEV_MODE=True)
class SyncTaskTest(TestCase):
    def test_task_calls_sync_and_returns_count(self) -> None:
        from apps.bexio.tasks import sync_lieferantenrechnungen_task

        count = sync_lieferantenrechnungen_task()
        assert count == _EXPECTED_ROW_COUNT


# ---------------------------------------------------------------------------
# Admin-Views
# ---------------------------------------------------------------------------


@override_settings(BEXIO_DEV_MODE=True)
class LieferantenrechnungAdminTest(TestCase):
    def setUp(self) -> None:
        self.superuser = User.objects.create_superuser(
            username="admin", password="adminpass"
        )
        self.client = Client()
        self.client.force_login(self.superuser)
        self.changelist_url = reverse("admin:bexio_lieferantenrechnung_changelist")

    def test_sync_view_runs_upsert(self) -> None:
        response = self.client.get(reverse("admin:bexio_lieferantenrechnung_sync"))
        self.assertEqual(response.status_code, 302)
        assert _LieferantenrechnungModel.objects.count() == _EXPECTED_ROW_COUNT

    def test_full_sync_view_clears_and_reloads(self) -> None:
        sync_lieferantenrechnungen()
        response = self.client.get(reverse("admin:bexio_lieferantenrechnung_full_sync"))
        self.assertEqual(response.status_code, 302)
        assert _LieferantenrechnungModel.objects.count() == _EXPECTED_ROW_COUNT

    def test_sync_view_shows_error_on_exception(self) -> None:
        with patch("apps.bexio.sync.sync_lieferantenrechnungen") as mock_sync:
            mock_sync.side_effect = RuntimeError("API down")
            response = self.client.get(reverse("admin:bexio_lieferantenrechnung_sync"))
        self.assertEqual(response.status_code, 302)

    def test_full_sync_view_shows_error_on_exception(self) -> None:
        with patch("apps.bexio.sync.full_sync_lieferantenrechnungen") as mock_full:
            mock_full.side_effect = RuntimeError("API down")
            response = self.client.get(
                reverse("admin:bexio_lieferantenrechnung_full_sync")
            )
        self.assertEqual(response.status_code, 302)

    def test_has_no_add_permission(self) -> None:
        response = self.client.get(reverse("admin:bexio_lieferantenrechnung_add"))
        self.assertEqual(response.status_code, 403)

    def test_changelist_accessible(self) -> None:
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Konto-Sync
# ---------------------------------------------------------------------------


@override_settings(BEXIO_DEV_MODE=True)
class SyncKontenTest(TestCase):
    def test_sync_creates_konten(self) -> None:
        count = sync_konten()
        assert count == _EXPECTED_KONTO_COUNT
        assert _KontoModel.objects.count() == _EXPECTED_KONTO_COUNT

    def test_sync_is_idempotent(self) -> None:
        sync_konten()
        sync_konten()
        assert _KontoModel.objects.count() == _EXPECTED_KONTO_COUNT

    def test_sync_returns_zero_for_empty_response(self) -> None:
        with patch("apps.bexio.sync.BexioClient") as MockClient:
            MockClient.return_value.get_all_accounts.return_value = []
            count = sync_konten()
        assert count == 0

    def test_full_sync_deletes_and_recreates(self) -> None:
        sync_konten()
        count = full_sync_konten()
        assert count == _EXPECTED_KONTO_COUNT
        assert _KontoModel.objects.count() == _EXPECTED_KONTO_COUNT

    def test_full_sync_restores_buchungskonto_on_rechnungen(self) -> None:
        sync_konten()
        sync_lieferantenrechnungen()
        mit_konto = _LieferantenrechnungModel.objects.filter(
            buchungskonto__isnull=False
        ).count()
        assert mit_konto > 0
        full_sync_konten()
        assert (
            _LieferantenrechnungModel.objects.filter(
                buchungskonto__isnull=False
            ).count()
            == mit_konto
        )

    def test_upsert_overwrites_changed_name(self) -> None:
        sync_konten()
        _KontoModel.objects.filter(bexio_int_id=1).update(name="GEAENDERT")
        sync_konten()
        assert _KontoModel.objects.get(bexio_int_id=1).name == "Apparate"

    def test_konto_str(self) -> None:
        sync_konten()
        konto = Konto.filter(bexio_int_id=1).first()
        assert konto is not None
        assert str(konto) == "4001 Apparate"


@override_settings(BEXIO_DEV_MODE=True)
class ResolvKontoTest(TestCase):
    """_resolve_konto triggert Konto-Sync wenn Konto fehlt."""

    def test_resolve_konto_found_directly(self) -> None:
        sync_konten()
        from apps.bexio.sync import _resolve_konto

        konto = _resolve_konto(1)
        assert konto is not None

    def test_resolve_konto_triggers_sync_when_missing(self) -> None:
        # Noch kein Konto in DB — _resolve_konto soll Sync anstoßen
        from apps.bexio.sync import _resolve_konto

        assert _KontoModel.objects.count() == 0
        konto = _resolve_konto(1)
        assert konto is not None
        assert _KontoModel.objects.count() == _EXPECTED_KONTO_COUNT

    def test_resolve_konto_prints_error_when_not_found_after_sync(self) -> None:
        from apps.bexio.sync import _resolve_konto

        with patch("apps.bexio.sync.sync_konten"):
            result = _resolve_konto(9999)
        assert result is None


# ---------------------------------------------------------------------------
# BexioClient — get_all_accounts
# ---------------------------------------------------------------------------


@override_settings(BEXIO_DEV_MODE=True)
class BexioClientKontenDevModeTest(TestCase):
    def test_dev_mode_returns_fixture(self) -> None:
        from apps.bexio.services import _DEV_FIXTURE_KONTEN, BexioClient

        client = BexioClient()
        assert client.get_all_accounts() == _DEV_FIXTURE_KONTEN


@override_settings(BEXIO_DEV_MODE=False, BEXIO_ACCESS_TOKEN="test-token")
class BexioClientKontenRealApiTest(TestCase):
    def _make_response(self, data: list[Any], status_code: int = 200) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = data
        resp.raise_for_status = MagicMock()
        return resp

    def test_get_all_accounts_calls_correct_url(self) -> None:
        from apps.bexio.services import BexioClient

        fake_accounts = [{"id": 89, "account_no": "9901", "name": "Test"}]
        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.return_value = self._make_response(fake_accounts)
            client = BexioClient()
            result = client.get_all_accounts()

        assert result == fake_accounts
        call_url = mock_get.call_args[0][0]
        assert "/2.0/accounts" in call_url


# ---------------------------------------------------------------------------
# Celery Task — Konto
# ---------------------------------------------------------------------------


@override_settings(BEXIO_DEV_MODE=True)
class SyncKontenTaskTest(TestCase):
    def test_task_calls_sync_and_returns_count(self) -> None:
        from apps.bexio.tasks import sync_konten_task

        count = sync_konten_task()
        assert count == _EXPECTED_KONTO_COUNT


# ---------------------------------------------------------------------------
# Admin-Views — Konto
# ---------------------------------------------------------------------------


@override_settings(BEXIO_DEV_MODE=True)
class KontoAdminTest(TestCase):
    def setUp(self) -> None:
        self.superuser = User.objects.create_superuser(
            username="admin", password="adminpass"
        )
        self.client = Client()
        self.client.force_login(self.superuser)
        self.changelist_url = reverse("admin:bexio_konto_changelist")

    def test_sync_view_creates_konten(self) -> None:
        response = self.client.get(reverse("admin:bexio_konto_sync"))
        self.assertEqual(response.status_code, 302)
        assert _KontoModel.objects.count() == _EXPECTED_KONTO_COUNT

    def test_full_sync_view_clears_and_reloads(self) -> None:
        sync_konten()
        response = self.client.get(reverse("admin:bexio_konto_full_sync"))
        self.assertEqual(response.status_code, 302)
        assert _KontoModel.objects.count() == _EXPECTED_KONTO_COUNT

    def test_sync_view_shows_error_on_exception(self) -> None:
        with patch("apps.bexio.sync.sync_konten") as mock_sync:
            mock_sync.side_effect = RuntimeError("API down")
            response = self.client.get(reverse("admin:bexio_konto_sync"))
        self.assertEqual(response.status_code, 302)

    def test_full_sync_view_shows_error_on_exception(self) -> None:
        with patch("apps.bexio.sync.full_sync_konten") as mock_full:
            mock_full.side_effect = RuntimeError("API down")
            response = self.client.get(reverse("admin:bexio_konto_full_sync"))
        self.assertEqual(response.status_code, 302)

    def test_has_no_add_permission(self) -> None:
        response = self.client.get(reverse("admin:bexio_konto_add"))
        self.assertEqual(response.status_code, 403)

    def test_changelist_accessible(self) -> None:
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
