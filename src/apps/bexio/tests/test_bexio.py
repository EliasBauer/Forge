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

# Dev-Fixture hat 3 Bills mit 1 + 2 + 1 = 4 Zeilenpositionen
_EXPECTED_ROW_COUNT = 4
# Dev-Fixture für Konten hat 4 Einträge
_EXPECTED_KONTO_COUNT = 4

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
        # Bill 01558 hat titel="1" → kein 900.-Prefix → richtiger_titel == titel
        rechnung = _LieferantenrechnungModel.objects.get(dokument_nr="01558")
        assert rechnung.richtiger_titel == "1"

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
    def _make_response(self, data: list[Any], status_code: int = 200) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = data
        resp.raise_for_status = MagicMock()
        return resp

    def test_headers_contain_bearer_token(self) -> None:
        from apps.bexio.services import BexioClient

        client = BexioClient()
        assert client._headers["Authorization"] == "Bearer test-token"
        assert client._headers["Accept"] == "application/json"

    def test_get_all_bills_single_page(self) -> None:
        from apps.bexio.services import BexioClient

        fake_bills = [{"id": f"id-{i}"} for i in range(3)]
        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.return_value = self._make_response(fake_bills)
            client = BexioClient()
            result = client.get_all_bills()

        assert result == fake_bills
        assert mock_get.call_count == 1

    def test_get_all_bills_paginates(self) -> None:
        from apps.bexio.services import _PAGE_SIZE, BexioClient

        full_page = [{"id": f"id-{i}"} for i in range(_PAGE_SIZE)]
        last_page = [{"id": "id-last"}]

        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.side_effect = [
                self._make_response(full_page),
                self._make_response(last_page),
            ]
            client = BexioClient()
            result = client.get_all_bills()

        assert len(result) == _PAGE_SIZE + 1
        assert mock_get.call_count == 2

    def test_get_all_bills_handles_dict_with_data_key(self) -> None:
        from apps.bexio.services import BexioClient

        fake_bills = [{"id": "abc"}]
        wrapped = {"data": fake_bills, "paging": {"total": 1}}
        with patch("apps.bexio.services.requests.get") as mock_get:
            mock_get.return_value = self._make_response(wrapped)  # type: ignore[arg-type]
            client = BexioClient()
            result = client.get_all_bills()

        assert result == fake_bills


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
