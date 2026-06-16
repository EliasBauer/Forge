from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.utils.dateparse import parse_date, parse_datetime

from apps.bexio.services import BexioClient

if TYPE_CHECKING:
    from apps.bexio.models import Konto

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Konten
# ------------------------------------------------------------------


def sync_konten() -> int:
    """
    Holt alle Konten von Bexio und spiegelt sie in der DB (Upsert via bexio_id).
    Gibt die Anzahl verarbeiteter Einträge zurück.
    """
    from apps.bexio.models import Konto

    client = BexioClient()
    accounts = client.get_all_accounts()

    if not accounts:
        logger.info("bexio sync: keine Konten erhalten")
        return 0

    for account in accounts:
        bexio_int_id = account["id"]
        data = {
            "bexio_id": uuid.UUID(account["uuid"]),
            "bexio_int_id": bexio_int_id,
            "account_no": account.get("account_no") or "",
            "name": account.get("name") or "",
            "account_type": account.get("account_type") or 0,
            "tax_id": account.get("tax_id"),
            "fibu_account_group_id": account.get("fibu_account_group_id"),
            "is_active": bool(account.get("is_active", True)),
            "is_locked": bool(account.get("is_locked", False)),
        }
        existing = Konto.filter(bexio_int_id=bexio_int_id).first()
        if existing is not None:
            existing.update(creator_id=None, ignore_permission=True, **data)
        else:
            Konto.create(creator_id=None, ignore_permission=True, **data)

    logger.info("bexio sync: %d Konten verarbeitet", len(accounts))
    return len(accounts)


def full_sync_konten() -> int:
    """Löscht alle lokalen Konten und lädt alles neu von Bexio."""
    from apps.bexio.models import Konto

    for konto in Konto.all():
        konto.delete(creator_id=None, ignore_permission=True)

    logger.info("bexio full sync: alle Konten gelöscht")
    return sync_konten()


# ------------------------------------------------------------------
# Lieferantenrechnungen
# ------------------------------------------------------------------


def _resolve_konto(bexio_konto_id: int) -> Konto | None:
    """
    Sucht ein Konto per bexio_id. Ist es nicht vorhanden, wird einmalig
    ein Konto-Sync angestoßen und danach erneut gesucht.
    """
    from apps.bexio.models import Konto

    konto = Konto.filter(bexio_int_id=bexio_konto_id).first()
    if konto is None:
        logger.info(
            "bexio sync: Konto int_id=%d nicht gefunden, starte Konto-Sync",
            bexio_konto_id,
        )
        sync_konten()
        konto = Konto.filter(bexio_int_id=bexio_konto_id).first()
        if konto is None:
            print(
                f"[bexio sync] FEHLER: Konto bexio_int_id={bexio_konto_id} "
                "nach Sync immer noch nicht gefunden"
            )
    return konto


def compute_correct_title(title: str, document_no: str) -> str:
    if title.startswith("900."):
        return document_no
    return title


def _bill_to_rows(bill: dict[str, Any]) -> list[dict[str, Any]]:
    """Flacht eine Bill mit N line_items in N Dicts auf (eines pro Zeilenposition)."""
    titel = bill.get("title") or ""
    dokument_nr = bill.get("document_no") or ""

    bill_header = {
        "bexio_id": uuid.UUID(bill["id"]),
        "dokument_nr": dokument_nr,
        "titel": titel,
        "richtiger_titel": compute_correct_title(titel, dokument_nr),
        "status": bill.get("status") or "",
        "rechnungsdatum": parse_date(bill["bill_date"]),
        "faelligkeitsdatum": (
            parse_date(bill["due_date"]) if bill.get("due_date") else None
        ),
        "lieferant_id": bill["supplier_id"],
        "firmenname": bill.get("lastname_company") or "",
        "verkaeufer_ref": bill.get("vendor_ref"),
        "waehrung_code": bill.get("currency_code") or "CHF",
        "rechnungsbetrag": Decimal(str(bill.get("amount_calc") or 0)),
        "ausstehender_betrag": Decimal(str(bill.get("pending_amount") or 0)),
        "ueberfaellig": bool(bill.get("overdue", False)),
        "bexio_erstellt_am": parse_datetime(bill["created_at"]),
    }

    rows = []
    for item in bill.get("line_items") or []:
        rows.append(
            {
                **bill_header,
                "bexio_zeilen_id": uuid.UUID(item["id"]),
                "position": item.get("position") or 0,
                "betrag": Decimal(str(item.get("amount") or 0)),
                "zeilen_titel": item.get("title"),
                "steuer_berechnet": Decimal(str(item.get("tax_calc") or 0)),
                # raw bexio-ID; wird in sync_lieferantenrechnungen aufgelöst
                "_bexio_buchungskonto_id": item.get("booking_account_id"),
            }
        )

    return rows


def sync_lieferantenrechnungen() -> int:
    """
    Holt alle Lieferantenrechnungen von Bexio und spiegelt sie in der DB.
    Erstellt neue Einträge, aktualisiert geänderte. Ein Eintrag pro Zeilenposition.
    Gibt die Anzahl verarbeiteter Datensätze zurück.
    """
    from apps.bexio.models import Lieferantenrechnung

    client = BexioClient()
    bills = client.get_all_bills()

    if not bills:
        logger.info("bexio sync: keine Lieferantenrechnungen erhalten")
        return 0

    rows = []
    for bill in bills:
        rows.extend(_bill_to_rows(bill))

    for row in rows:
        bexio_konto_id: int | None = row.pop("_bexio_buchungskonto_id", None)
        row["buchungskonto"] = (
            _resolve_konto(bexio_konto_id) if bexio_konto_id is not None else None
        )

        bexio_zeilen_id = row["bexio_zeilen_id"]
        existing = Lieferantenrechnung.filter(bexio_zeilen_id=bexio_zeilen_id).first()
        if existing is not None:
            existing.update(
                creator_id=None,
                ignore_permission=True,
                **{k: v for k, v in row.items() if k != "bexio_zeilen_id"},
            )
        else:
            Lieferantenrechnung.create(creator_id=None, ignore_permission=True, **row)

    logger.info("bexio sync: %d Zeilenpositionen verarbeitet", len(rows))
    return len(rows)


def full_sync_lieferantenrechnungen() -> int:
    """
    Vollständige Aktualisierung: löscht alle lokalen Einträge und lädt
    alles neu von Bexio. Nur für Admin-Nutzung.
    """
    from apps.bexio.models import Lieferantenrechnung

    for data in Lieferantenrechnung.all():
        data.delete(creator_id=None, ignore_permission=True)

    logger.info("bexio full sync: alle Einträge gelöscht")

    return sync_lieferantenrechnungen()
