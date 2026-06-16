from __future__ import annotations

from django.db import models
from general_manager import (
    AdditiveManagerPermission,
    GeneralManager,
    ReadOnlyInterface,
)


class Kostenart(GeneralManager):
    """Statische Liste aller Kostenarten."""

    id: int
    schluessel: str
    name: str
    ist_ertragsblock: bool
    konto_nummer: int | None
    reihenfolge: int

    _data = [
        {
            "schluessel": "regie",
            "name": "Regie",
            "ist_ertragsblock": True,
            "konto_nummer": None,
            "reihenfolge": 1,
        },
        {
            "schluessel": "nachtrag",
            "name": "Nachtrag",
            "ist_ertragsblock": True,
            "konto_nummer": None,
            "reihenfolge": 2,
        },
        {
            "schluessel": "apparate",
            "name": "Apparate",
            "ist_ertragsblock": False,
            "konto_nummer": 4001,
            "reihenfolge": 3,
        },
        {
            "schluessel": "kanaele_rohre",
            "name": "Kanäle und Rohre",
            "ist_ertragsblock": False,
            "konto_nummer": 4002,
            "reihenfolge": 4,
        },
        {
            "schluessel": "armaturen",
            "name": "Armaturen",
            "ist_ertragsblock": False,
            "konto_nummer": 4003,
            "reihenfolge": 5,
        },
        {
            "schluessel": "regulierung",
            "name": "Regulierung",
            "ist_ertragsblock": False,
            "konto_nummer": 4004,
            "reihenfolge": 6,
        },
        {
            "schluessel": "schaltschrank",
            "name": "Schaltschrank",
            "ist_ertragsblock": False,
            "konto_nummer": 4005,
            "reihenfolge": 7,
        },
        {
            "schluessel": "transport_montage",
            "name": "Transport und Montage",
            "ist_ertragsblock": False,
            "konto_nummer": 44401,
            "reihenfolge": 8,
        },
        {
            "schluessel": "stunden",
            "name": "Stunden",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 9,
        },
        {
            "schluessel": "transport_montage_fremd",
            "name": "Transport und Montage – Fremdleistung",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 10,
        },
        {
            "schluessel": "isolation",
            "name": "Isolation",
            "ist_ertragsblock": False,
            "konto_nummer": 4402,
            "reihenfolge": 11,
        },
        {
            "schluessel": "dienstleistung",
            "name": "Dienstleistung",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 12,
        },
        {
            "schluessel": "diverses",
            "name": "Diverses",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 13,
        },
        {
            "schluessel": "planung",
            "name": "Planung",
            "ist_ertragsblock": False,
            "konto_nummer": 4403,
            "reihenfolge": 14,
        },
        {
            "schluessel": "gemeinkosten",
            "name": "Gemeinkosten",
            "ist_ertragsblock": False,
            "konto_nummer": None,
            "reihenfolge": 15,
        },
    ]

    class Interface(ReadOnlyInterface):
        schluessel = models.CharField(max_length=50, unique=True)
        name = models.CharField(max_length=200)
        ist_ertragsblock = models.BooleanField(default=False)
        konto_nummer = models.IntegerField(null=True, blank=True)
        reihenfolge = models.PositiveSmallIntegerField(default=0)

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
