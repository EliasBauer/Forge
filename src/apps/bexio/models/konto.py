from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.db import models
from general_manager import AdditiveManagerPermission, DatabaseInterface, GeneralManager
from general_manager.bucket import Bucket

if TYPE_CHECKING:
    from apps.bexio.models.lieferantenrechnung import Lieferantenrechnung


class Konto(GeneralManager):
    """Spiegel der Bexio-Konten (accounts). Bexio gewinnt immer."""

    id: int
    bexio_id: uuid.UUID
    bexio_int_id: int
    account_no: str
    name: str
    account_type: int
    tax_id: int | None
    fibu_account_group_id: int | None
    is_active: bool
    is_locked: bool

    lieferantenrechnung_list: Bucket[Lieferantenrechnung]

    class Interface(DatabaseInterface):
        bexio_id = models.UUIDField(unique=True)
        bexio_int_id = models.IntegerField(unique=True)
        account_no = models.CharField(max_length=20)
        name = models.CharField(max_length=200)
        account_type = models.IntegerField(default=0)
        tax_id = models.IntegerField(null=True, blank=True)
        fibu_account_group_id = models.IntegerField(null=True, blank=True)
        is_active = models.BooleanField(default=True)
        is_locked = models.BooleanField(default=False)

        class Meta:
            verbose_name = "Konto"
            verbose_name_plural = "Konten"
            ordering = ["account_no"]

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["isAdmin"]
        __update__ = ["isAdmin"]
        __delete__ = ["isAdmin"]

    def __str__(self) -> str:
        return f"{self.account_no} {self.name}"
