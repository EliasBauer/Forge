from __future__ import annotations

from decimal import Decimal

from general_manager import GeneralManager, Input
from general_manager.api.property import graph_ql_property
from general_manager.cache.cache_decorator import cached
from general_manager.interface import CalculationInterface
from general_manager.measurement import Measurement

from apps.authentication.permission import CalculationPermission
from apps.bexio.models import Lieferantenrechnung
from apps.projekt.models import Kostenart, Projekt


class IstWert(GeneralManager):
    projekt: Projekt
    kostenart: Kostenart

    class Interface(CalculationInterface):
        projekt = Input(Projekt, possible_values=lambda: Projekt.all())
        kostenart = Input(Kostenart, possible_values=lambda: Kostenart.all())

    Permission = CalculationPermission

    @cached
    def _rechnungen_nach_konto(
        self,
    ) -> dict[str | None, tuple[Lieferantenrechnung, ...]]:
        result: dict[str | None, list[Lieferantenrechnung]] = {}
        for r in Lieferantenrechnung.filter(
            richtiger_titel=self.projekt.auftragsnummer
        ):
            key = r.buchungskonto.account_no if r.buchungskonto is not None else None
            result.setdefault(key, []).append(r)
        return {k: tuple(v) for k, v in result.items()}

    @graph_ql_property
    def ist_kosten_wert(self) -> Measurement | None:
        if self.kostenart.ist_ertragsblock:
            return None
        if self.kostenart.schluessel in ("stunden", "transport_montage"):
            return None  # TODO stunden.md

        index = self._rechnungen_nach_konto()

        if self.kostenart.schluessel == "diverses":
            bekannte = frozenset(
                str(k.konto_nummer)
                for k in Kostenart.all()
                if k.konto_nummer is not None
            )
            rechnungen = [
                r
                for key, gruppe in index.items()
                if key is None or key not in bekannte
                for r in gruppe
            ]
            if not rechnungen:
                return None
            summe = sum(
                (r.betrag - r.steuer_berechnet for r in rechnungen), Decimal("0")
            )
            return Measurement(summe, "CHF")

        konto_nr = self.kostenart.konto_nummer
        if konto_nr is None:
            return None
        rechnungen = list(index.get(str(konto_nr), ()))
        if not rechnungen:
            return None
        summe = sum((r.betrag - r.steuer_berechnet for r in rechnungen), Decimal("0"))
        return Measurement(summe, "CHF")

    @graph_ql_property
    def ist_kosten_wert_prozent(self) -> Decimal | None:
        ist = self.ist_kosten_wert
        if ist is None:
            return None
        rechnungen = [
            r for gruppe in self._rechnungen_nach_konto().values() for r in gruppe
        ]
        summe_ist = sum(
            (r.betrag - r.steuer_berechnet for r in rechnungen), Decimal("0")
        )
        if not summe_ist:
            return None
        return Decimal(ist.magnitude / summe_ist * 100).quantize(Decimal("0.01"))
