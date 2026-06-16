from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Manager, QuerySet
from general_manager import (
    AdditiveManagerPermission,
    DatabaseInterface,
    GeneralManager,
)
from general_manager.bucket import Bucket
from general_manager.measurement import Measurement, MeasurementField
from general_manager.rule import Rule

if TYPE_CHECKING:
    from apps.projekt.models import KostenPosition


class _ProjectManager(Manager):  # type: ignore[type-arg]
    def get_queryset(self) -> QuerySet[Any]:
        return super().get_queryset().select_related("projektleiter")


class Projekt(GeneralManager):
    """Projektübersicht – Ablösung der Excel-Datei."""

    id: int
    name: str
    auftragsnummer: str
    jahr: int
    projektleiter: User | None
    offerte_summe: Measurement
    wv_summe: Measurement | None
    auftrag_fertig: bool

    kostenposition_list: Bucket[KostenPosition]

    class Interface(DatabaseInterface):
        objects = _ProjectManager()

        name = models.CharField(max_length=200)
        auftragsnummer = models.CharField(max_length=50, unique=True)
        jahr = models.PositiveIntegerField()
        projektleiter = models.ForeignKey(
            "auth.User",
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
            related_name="projekte",
        )
        offerte_summe = MeasurementField(base_unit="CHF")
        wv_summe = MeasurementField(
            base_unit="CHF", default=None, null=True, blank=True
        )
        auftrag_fertig = models.BooleanField(default=False)

        class Meta:
            verbose_name = "Projekt"
            verbose_name_plural = "Projekte"
            rules = [
                Rule["Projekt"](lambda x: x.offerte_summe > "0 CHF"),
                Rule["Projekt"](lambda x: x.wv_summe > "0 CHF"),  # type: ignore[operator]
            ]

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAdminGroup", "isProjektleiter", "isBetrachter"]
        __create__ = ["isAdminGroup", "isProjektleiter"]
        __update__ = ["isAdminGroup", "isProjektleiter"]
        __delete__ = ["isAdminGroup", "isProjektleiter"]

        # auftragsnummer = {"update": ["isAdmin"]}

    @classmethod
    def create(
        cls,
        creator_id: int | None = None,
        history_comment: str | None = None,
        ignore_permission: bool = False,
        **kwargs: Any,
    ) -> Projekt:
        if "projektleiter" in kwargs and kwargs["projektleiter"] is not None:
            kwargs["projektleiter_id"] = int(kwargs.pop("projektleiter"))
        return super().create(
            creator_id=creator_id,
            history_comment=history_comment,
            ignore_permission=ignore_permission,
            **kwargs,
        )

    def update(
        self,
        creator_id: int | None = None,
        history_comment: str | None = None,
        ignore_permission: bool = False,
        **kwargs: Any,
    ) -> Projekt:
        if "projektleiter" in kwargs and kwargs["projektleiter"] is not None:
            kwargs["projektleiter_id"] = int(kwargs.pop("projektleiter"))
        return super().update(
            creator_id=creator_id,
            history_comment=history_comment,
            ignore_permission=ignore_permission,
            **kwargs,
        )
