from __future__ import annotations

from django.db import models
from general_manager import (
    AdditiveManagerPermission,
    DatabaseInterface,
    GeneralManager,
)
from general_manager.measurement import Measurement, MeasurementField
from general_manager.rule import Rule


class Stundensatz(GeneralManager):
    """Globaler Stundensatz pro Kalenderjahr für Personalkosten-Kalkulation."""

    id: int
    jahr: int
    stundensatz: Measurement

    class Interface(DatabaseInterface):
        jahr = models.PositiveIntegerField(unique=True)
        stundensatz = MeasurementField(base_unit="CHF")

        class Meta:
            verbose_name = "Stundensatz"
            verbose_name_plural = "Stundensätze"
            rules = [Rule["Stundensatz"](lambda x: x.stundensatz > "0 CHF")]

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAdminGroup", "isProjektleiter", "isBetrachter"]
        __create__ = ["isAdminGroup", "isProjektleiter"]
        __update__ = ["isAdminGroup", "isProjektleiter"]
        __delete__ = ["isAdminGroup", "isProjektleiter"]
