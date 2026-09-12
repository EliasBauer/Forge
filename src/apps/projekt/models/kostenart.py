from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from general_manager import (
    AdditiveManagerPermission,
    GeneralManager,
    ReadOnlyInterface,
)

if TYPE_CHECKING:
    from general_manager.bucket import Bucket

    from apps.projekt.models.kosten_position import KostenPosition


class Kostenart(GeneralManager):
    """Statische Liste aller Kostenarten."""

    _data = [
        {
            "id": 1,
            "schluessel": "regie",
            "name": "Regie",
            "ist_ertragsblock": True,
            "konto_nummer": None,
            "reihenfolge": 1,
            "is_active": True,
        },
        {
            "id": 2,
            "schluessel": "nachtrag",
            "name": "Nachtrag",
            "ist_ertragsblock": True,
            "konto_nummer": None,
            "reihenfolge": 2,
            "is_active": True,
        },
        {
            "id": 3,
            "schluessel": "apparate",
            "name": "Apparate",
            "ist_ertragsblock": False,
            "konto_nummer": 4001,
            "reihenfolge": 3,
            "is_active": True,
        },
        {
            "id": 4,
            "schluessel": "kanaele_rohre",
            "name": "Kanäle und Rohre",
            "ist_ertragsblock": False,
            "konto_nummer": 4002,
            "reihenfolge": 4,
            "is_active": True,
        },
        {
            "id": 5,
            "schluessel": "armaturen",
            "name": "Armaturen",
            "ist_ertragsblock": False,
            "konto_nummer": 4003,
            "reihenfolge": 5,
            "is_active": True,
        },
        {
            "id": 6,
            "schluessel": "regulierung",
            "name": "Regulierung",
            "ist_ertragsblock": False,
            "konto_nummer": 4004,
            "reihenfolge": 6,
            "is_active": True,
        },
        {
            "id": 7,
            "schluessel": "schaltschrank",
            "name": "Schaltschrank",
            "ist_ertragsblock": False,
            "konto_nummer": 4005,
            "reihenfolge": 7,
            "is_active": True,
        },
        {
            "id": 8,
            "schluessel": "transport_montage",
            "name": "Transport und Montage",
            "ist_ertragsblock": False,
            "konto_nummer": 44401,
            "reihenfolge": 8,
            "is_active": True,
        },
        {
            "id": 9,
            "schluessel": "stunden",
            "name": "Stunden",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 9,
            "is_active": True,
        },
        {
            "id": 10,
            "schluessel": "transport_montage_fremd",
            "name": "Transport und Montage – Fremdleistung",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 10,
            "is_active": True,
        },
        {
            "id": 11,
            "schluessel": "isolation",
            "name": "Isolation",
            "ist_ertragsblock": False,
            "konto_nummer": 4402,
            "reihenfolge": 11,
            "is_active": True,
        },
        {
            "id": 12,
            "schluessel": "dienstleistung",
            "name": "Dienstleistung",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 12,
            "is_active": True,
        },
        {
            "id": 13,
            "schluessel": "diverses",
            "name": "Diverses",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 13,
            "is_active": True,
        },
        {
            "id": 14,
            "schluessel": "planung",
            "name": "Planung",
            "ist_ertragsblock": False,
            "konto_nummer": 4403,
            "reihenfolge": 14,
            "is_active": True,
        },
        {
            "id": 15,
            "schluessel": "gemeinkosten",
            "name": "Gemeinkosten",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 15,
            "is_active": True,
        },
    ]

    id: int
    schluessel: str
    name: str
    ist_ertragsblock: bool
    konto_nummer: int | None
    reihenfolge: int
    is_active: bool

    kosten_positionen_list: Bucket[KostenPosition]

    def __str__(self) -> str:
        return self.name

    class Interface(ReadOnlyInterface):
        schluessel = models.CharField(max_length=50, unique=True)
        name = models.CharField(max_length=200)
        ist_ertragsblock = models.BooleanField(default=False)
        konto_nummer = models.IntegerField(null=True, blank=True)
        reihenfolge = models.PositiveSmallIntegerField(default=0)
        is_active = models.BooleanField(default=True)

        class Meta:
            verbose_name = "Kostenart"
            verbose_name_plural = "Kostenarten"
            db_table = "projekt_kostenart"
            ordering = ["reihenfolge"]

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["isAdmin"]
        __update__ = ["isAdmin"]
        __delete__ = ["isAdmin"]
