from __future__ import annotations

from typing import Any

import requests
from django.conf import settings

BEXIO_API_BASE = "https://api.bexio.com"
_PAGE_SIZE = 100

_DEV_FIXTURE_KONTEN: list[dict[str, Any]] = [
    {
        "id": 1,
        "uuid": "00000000-0000-0000-0000-000000000001",
        "account_no": "4001",
        "name": "Apparate",
        "account_type": 1,
        "tax_id": None,
        "fibu_account_group_id": None,
        "is_active": True,
        "is_locked": False,
    },
    {
        "id": 2,
        "uuid": "00000000-0000-0000-0000-000000000002",
        "account_no": "4002",
        "name": "Kanäle und Rohre",
        "account_type": 1,
        "tax_id": None,
        "fibu_account_group_id": None,
        "is_active": True,
        "is_locked": False,
    },
    {
        "id": 3,
        "uuid": "00000000-0000-0000-0000-000000000003",
        "account_no": "4003",
        "name": "Armaturen",
        "account_type": 1,
        "tax_id": None,
        "fibu_account_group_id": None,
        "is_active": True,
        "is_locked": False,
    },
    {
        "id": 4,
        "uuid": "00000000-0000-0000-0000-000000000004",
        "account_no": "4004",
        "name": "Regulierung",
        "account_type": 1,
        "tax_id": None,
        "fibu_account_group_id": None,
        "is_active": True,
        "is_locked": False,
    },
    # weitere Einträge nach Bedarf ergänzen
]

# Dev-Fixture: repräsentative Beispieldatensätze (kein echter API-Zugriff nötig)
_DEV_FIXTURE: list[dict[str, Any]] = [
    {
        "id": "724fa4a5-3777-4d5e-9177-d969a9f6271d",
        "document_no": "01558",
        "title": "1",
        "status": "BOOKED",
        "bill_date": "2026-04-07",
        "due_date": "2026-05-07",
        "supplier_id": 144,
        "lastname_company": "dresohn AG",
        "vendor_ref": "110015415",
        "currency_code": "CHF",
        "amount_calc": 2309.10,
        "pending_amount": 2309.10,
        "overdue": False,
        "line_items": [
            {
                "id": "bcc3c63c-c857-46e7-b6c6-265f1eab9dd2",
                "position": 0,
                "amount": 2309.10,
                "title": None,
                "tax_id": 35,
                "tax_man": 0.0,
                "tax_calc": 173.02,
                "booking_account_id": 1,
            }
        ],
        "created_at": "2026-04-07T11:05:08+0000",
    },
    {
        "id": "a1b2c3d4-0001-0001-0001-000000000001",
        "document_no": "01500",
        "title": "1",
        "status": "BOOKED",
        "bill_date": "2026-01-15",
        "due_date": "2026-02-15",
        "supplier_id": 87,
        "lastname_company": "Lüftung Müller GmbH",
        "vendor_ref": "REF-0312",
        "currency_code": "CHF",
        "amount_calc": 9600.00,
        "pending_amount": 0.00,
        "overdue": False,
        "line_items": [
            {
                "id": "aaaaaaaa-0001-0001-0001-000000000001",
                "position": 0,
                "amount": 4800.00,
                "title": None,
                "tax_id": 35,
                "tax_man": 0.0,
                "tax_calc": 360.00,
                "booking_account_id": 2,
            },
            {
                "id": "aaaaaaaa-0001-0001-0001-000000000002",
                "position": 1,
                "amount": 4800.00,
                "title": None,
                "tax_id": 35,
                "tax_man": 0.0,
                "tax_calc": 360.00,
                "booking_account_id": 3,
            },
        ],
        "created_at": "2026-01-15T09:00:00+0000",
    },
    {
        # Fehlerfall: title beginnt mit '900.' → correct_title = document_no
        "id": "b2c3d4e5-0002-0002-0002-000000000002",
        "document_no": "1",
        "title": "900.2025.0198",
        "status": "BOOKED",
        "bill_date": "2025-11-03",
        "due_date": "2025-12-03",
        "supplier_id": 102,
        "lastname_company": "Rohrbau AG",
        "vendor_ref": None,
        "currency_code": "CHF",
        "amount_calc": 1250.50,
        "pending_amount": 1250.50,
        "overdue": True,
        "line_items": [
            {
                "id": "bbbbbbbb-0002-0002-0002-000000000002",
                "position": 0,
                "amount": 1250.50,
                "title": None,
                "tax_id": 35,
                "tax_man": 0.0,
                "tax_calc": 93.79,
                "booking_account_id": 4,
            }
        ],
        "created_at": "2025-11-03T14:30:00+0000",
    },
]


class BexioClient:
    """
    Client für die Bexio API (Lieferantenrechnungen).

    Im Dev-Modus (BEXIO_DEV_MODE=True oder kein BEXIO_ACCESS_TOKEN gesetzt)
    werden statt echter API-Calls lokale Fixture-Daten zurückgegeben.
    """

    def __init__(self) -> None:
        token = getattr(settings, "BEXIO_ACCESS_TOKEN", None)
        dev_mode = getattr(settings, "BEXIO_DEV_MODE", not bool(token))
        self._dev_mode: bool = dev_mode
        self._token: str | None = token

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    def get_all_accounts(self) -> list[dict[str, Any]]:
        """Gibt alle Konten zurück."""
        if self._dev_mode:
            return _DEV_FIXTURE_KONTEN

        response = requests.get(
            f"{BEXIO_API_BASE}/2.0/accounts",
            headers=self._headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def get_all_bills(self) -> list[dict[str, Any]]:
        """Gibt alle Lieferantenrechnungen zurück (paginiert)."""
        if self._dev_mode:
            return _DEV_FIXTURE

        results: list[dict[str, Any]] = []
        offset = 0
        while True:
            batch = self._fetch_bills_page(offset=offset, limit=_PAGE_SIZE)
            results.extend(batch)
            if len(batch) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        return results

    def _fetch_bills_page(self, offset: int, limit: int) -> list[dict[str, Any]]:
        url = f"{BEXIO_API_BASE}/4.0/purchase/bills"
        response = requests.get(
            url,
            headers=self._headers,
            params={"offset": offset, "limit": limit},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        # Bexio v4 list endpoints können {"data": [...]} oder direkt [...] zurückgeben
        if isinstance(result, dict):  # pragma: no branch
            for key in ("data", "bills", "items"):  # pragma: no branch
                if key in result and isinstance(result[key], list):  # pragma: no branch
                    return result[key]  # type: ignore[no-any-return]
        return result  # type: ignore[no-any-return]
