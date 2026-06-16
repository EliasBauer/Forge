from __future__ import annotations

from general_manager import GeneralManager
from general_manager.api.property import graph_ql_property
from general_manager.interface import CalculationInterface

from apps.authentication.permission import CalculationPermission
from apps.projekt.models.projekt import Projekt
from apps.stunden.models import Stundensatz


class AufgabenStundensatz(GeneralManager):
    """Berechnete Hilfestellung – welche Daten fehlen noch in Forge."""

    class Interface(CalculationInterface):
        pass

    Permission = CalculationPermission

    @graph_ql_property
    def fehlende_stundensatz_jahre(self) -> list[int]:
        jahre_projekte: set[int] = {p.jahr for p in Projekt.all()}
        jahre_stundensatz: set[int] = {s.jahr for s in Stundensatz.all()}
        return sorted(jahre_projekte - jahre_stundensatz)
