from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.db import models
from django.db.models import Manager, QuerySet
from general_manager import (
    AdditiveManagerPermission,
    DatabaseInterface,
    FieldConfig,
    GeneralManager,
    IndexConfig,
)
from general_manager.bucket import Bucket
from general_manager.measurement import Measurement, MeasurementField
from general_manager.permission import (
    GraphQLPermissionCapability,
    permission_capability,
)
from general_manager.rule import Rule

from apps.authentication.managers import Benutzer
from apps.projekt.models.projekt_status import ProjektStatus

if TYPE_CHECKING:
    from apps.projekt.models import KostenPosition


class _ProjectManager(Manager):  # type: ignore[type-arg]
    def get_queryset(self) -> QuerySet[Any]:
        # N+1-Vermeidung: projektleiter (User-FK) wird bei jeder Zeile in
        # projektList/projekt(id) gelesen; ohne select_related eine Extra-Query
        # pro Zeile.
        return super().get_queryset().select_related("projektleiter")


class Projekt(GeneralManager):
    """Projektübersicht – Ablösung der Excel-Datei."""

    id: int
    name: str
    auftragsnummer: str
    jahr: int
    projektleiter: Benutzer | None
    offerte_summe: Measurement
    wv_summe: Measurement | None
    projekt_status: ProjektStatus

    kosten_positionen_list: Bucket[KostenPosition]

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
        projekt_status = models.ForeignKey(
            "projekt.ProjektStatus",
            on_delete=models.PROTECT,
            related_name="projekte",
        )

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
        graphql_capabilities: ClassVar[tuple[GraphQLPermissionCapability, ...]] = ()

        # auftragsnummer = {"update": ["isAdmin"]}

    class SearchConfig:
        indexes = [
            IndexConfig(
                name="projekte",
                fields=[
                    "name",
                    "auftragsnummer",
                    FieldConfig(name="projektleiter__username", boost=1.5),
                ],
            )
        ]

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
        if kwargs.get("projekt_status") is None:
            kwargs["projekt_status"] = ProjektStatus.filter(name="Offen").first()
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


def _register_graphql_capabilities() -> None:
    """Von ProjektConfig.ready() aufgerufen, NICHT auf Modulebene.

    Projekt.Permission.graphql_capabilities = (...) auf Modulebene würde beim
    Import von projekt.py über Projekt.Permission (Metaclass-Zugriff) GMs
    Lazy-Attribute-Initialisierung auslösen, die den vollen App-Registry
    braucht (apps.get_models()). Zur normalen Django-Laufzeit ist das kein
    Problem (Modelle sind beim Import längst geladen) — mypys
    django-stubs-Plugin importiert Model-Module aber in einer Reihenfolge,
    in der die Registry noch nicht vollständig ist, und crasht dabei mit
    einem INTERNAL ERROR. ready() läuft garantiert erst NACH dem Laden aller
    Apps und wird von django-stubs nicht mit-ausgeführt.
    """
    Projekt.Permission.graphql_capabilities = (
        permission_capability(Projekt, "update", name="canUpdate"),
        permission_capability(Projekt, "delete", name="canDelete"),
    )
