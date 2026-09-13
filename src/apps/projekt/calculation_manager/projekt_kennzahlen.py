from __future__ import annotations

from decimal import Decimal

from general_manager import GeneralManager, Input
from general_manager.api.property import graph_ql_property
from general_manager.cache.cache_decorator import cached
from general_manager.interface import CalculationInterface
from general_manager.measurement import Measurement

from apps.authentication.permission import CalculationPermission
from apps.bexio.models import Lieferantenrechnung
from apps.projekt.models import KostenPosition, Projekt


class ProjektKennzahlen(GeneralManager):
    projekt: Projekt

    class Interface(CalculationInterface):
        projekt = Input(Projekt, possible_values=lambda: Projekt.all())

    class Permission(CalculationPermission):
        __read__ = ["isForgeAdmin", "isProjektleiter", "isBetrachter"]
        # Lieferantenrechnungen sind für Betrachter tabu (siehe 5180928);
        # __read__ dieses Managers ist weiter gefasst, deshalb der Override.
        rechnungen = {"read": ["isForgeAdmin", "isProjektleiter"]}

    @cached
    def _rechnungen(self) -> tuple[Lieferantenrechnung, ...]:
        return tuple(
            Lieferantenrechnung.filter(richtiger_titel=self.projekt.auftragsnummer)
        )

    @graph_ql_property
    def rechnungen(self) -> list[Lieferantenrechnung]:
        return list(self._rechnungen())

    @cached
    def _summe_ist(self) -> Decimal:
        rechnungen = self._rechnungen()
        if not rechnungen:
            return Decimal("0")
        return sum(
            (r.betrag - r.steuer_berechnet for r in rechnungen), Decimal("0")
        ).quantize(Decimal("0.01"))

    @cached
    def _summe_offerte(self) -> Decimal:
        summe = Decimal("0")
        for pos in KostenPosition.filter(projekt=self.projekt):
            if pos.art.ist_ertragsblock or pos.art.schluessel == "stunden":
                continue
            if pos.offerte_kosten_wert is not None:
                summe += Decimal(pos.offerte_kosten_wert.magnitude)
        return summe.quantize(Decimal("0.01"))

    @cached
    def _summe_wv(self) -> Decimal:
        summe = Decimal("0")
        for pos in KostenPosition.filter(projekt=self.projekt):
            if pos.art.ist_ertragsblock or pos.art.schluessel == "stunden":
                continue
            wv = pos.wv_kosten_wert
            if wv is not None:
                summe += Decimal(wv.magnitude)
        return summe.quantize(Decimal("0.01"))

    @graph_ql_property
    def summe_ist_kosten(self) -> Measurement:
        return Measurement(self._summe_ist(), "CHF")

    @graph_ql_property
    def summe_wv_plus(self) -> Measurement:
        # TODO: Ertragsblock-Zusätze (Phase 2)
        if self.projekt.wv_summe is None:
            return Measurement(Decimal("0"), "CHF")
        return Measurement(Decimal(self.projekt.wv_summe.magnitude), "CHF")

    @graph_ql_property
    def bisher_verrechnet(self) -> Measurement:
        # ist_erloese = 0 bis Phase 2
        return Measurement(
            (Decimal("0") - self._summe_ist()).quantize(Decimal("0.01")), "CHF"
        )

    @graph_ql_property
    def summe_offerte_kosten(self) -> Measurement:
        return Measurement(self._summe_offerte(), "CHF")

    @graph_ql_property
    def summe_wv_kosten(self) -> Measurement:
        return Measurement(self._summe_wv(), "CHF")

    @graph_ql_property
    def verbrauchsrate(self) -> Decimal | None:
        """Anteil der Ist-Kosten am Plan-WV (nicht an der Offerte).

        Bezugsgrösse ist die Plan-WV-Spalte derselben Fusszeile — dasselbe
        `_summe_wv()`, auf dem auch `delta_ist_plan_pct` rechnet. Gegen die
        Offerte gerechnet stünde in der Tabelle sonst ein Prozentwert, der zu
        keiner der beiden darüberliegenden Summen passt.
        """
        basis = self._summe_wv()
        if not basis:
            return None
        return (self._summe_ist() / basis * 100).quantize(Decimal("0.01"))

    @graph_ql_property
    def delta_wv_off(self) -> Measurement | None:
        basis = self._summe_offerte()
        if not basis:
            return None
        return Measurement((self._summe_wv() - basis).quantize(Decimal("0.01")), "CHF")

    @graph_ql_property
    def delta_wv_off_pct(self) -> Decimal | None:
        basis = self._summe_offerte()
        if not basis:
            return None
        return ((self._summe_wv() - basis) / basis * 100).quantize(Decimal("0.01"))

    @graph_ql_property
    def delta_ist_plan(self) -> Measurement | None:
        basis = self._summe_wv()
        if not basis:
            return None
        return Measurement((self._summe_ist() - basis).quantize(Decimal("0.01")), "CHF")

    @graph_ql_property
    def delta_ist_plan_pct(self) -> Decimal | None:
        basis = self._summe_wv()
        if not basis:
            return None
        return ((self._summe_ist() - basis) / basis * 100).quantize(Decimal("0.01"))
