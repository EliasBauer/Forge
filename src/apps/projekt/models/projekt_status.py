from __future__ import annotations

from django.db import models
from general_manager import (
    AdditiveManagerPermission,
    GeneralManager,
    ReadOnlyInterface,
)


class ProjektStatus(GeneralManager):
    """Statische Liste der Projekt-Status (Offen, In Arbeit, Fertig)."""

    id: int
    name: str

    _data = [
        {"name": "Offen"},
        {"name": "In Arbeit"},
        {"name": "Fertig"},
    ]

    class Interface(ReadOnlyInterface):
        name = models.CharField(max_length=50, unique=True)

        class Meta:
            verbose_name = "Projekt-Status"
            verbose_name_plural = "Projekt-Status"
            db_table = "projekt_projektstatus"

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["isAdmin"]
        __update__ = ["isAdmin"]
        __delete__ = ["isAdmin"]
