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

    from apps.projekt.models.projekt import Projekt


class ProjektStatus(GeneralManager):
    """Statische Liste der Projekt-Status (Offen, In Arbeit, Fertig)."""

    _data = [
        {"id": 1, "name": "Offen", "is_active": True},
        {"id": 2, "name": "In Arbeit", "is_active": True},
        {"id": 3, "name": "Fertig", "is_active": True},
    ]

    id: int
    is_active: bool
    name: str

    projekte_list: Bucket[Projekt]

    def __str__(self) -> str:
        return self.name

    class Interface(ReadOnlyInterface):
        is_active = models.BooleanField(default=True)
        name = models.CharField(max_length=50, unique=True)

        class Meta:
            verbose_name = "Projekt-Status"
            verbose_name_plural = "Projekt-Status"
            db_table = "projekt_projektstatus"
            ordering = ["id"]

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["isAdmin"]
        __update__ = ["isAdmin"]
        __delete__ = ["isAdmin"]
