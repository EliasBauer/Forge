from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models
from general_manager import (
    AdditiveManagerPermission,
    DatabaseInterface,
    GeneralManager,
)
from general_manager.api.property import graph_ql_property
from general_manager.measurement import Measurement, MeasurementField

from apps.stunden.models import Stundensatz

if TYPE_CHECKING:
    from apps.projekt.models import Kostenart, Projekt

_DREI_SCHLUSSEL = frozenset({"apparate", "kanaele_rohre", "armaturen"})


class KostenPosition(GeneralManager):
    """
    Eine Zeile in der Projekt-Detailansicht.

    Felder:
    - offerte_kosten_wert: manuell erfasster CHF-Wert (für STUNDEN: nicht gespeichert).
    """

    id: int
    projekt: Projekt
    art: Kostenart
    offerte_kosten_wert: Measurement | None

    class Interface(DatabaseInterface):
        projekt = models.ForeignKey(
            "projekt.Projekt",
            on_delete=models.CASCADE,
            related_name="kosten_positionen",
            editable=False,
        )
        art = models.ForeignKey(
            "projekt.Kostenart",
            on_delete=models.PROTECT,
            related_name="kosten_positionen",
            editable=False,
        )
        offerte_kosten_wert = MeasurementField(
            base_unit="CHF", null=True, blank=True, default="0 CHF"
        )

        class Meta:
            verbose_name = "Kostenposition"
            verbose_name_plural = "Kostenpositionen"
            unique_together = [("projekt", "art")]

    class Permission(AdditiveManagerPermission):
        __based_on__ = "projekt"

    # ------------------------------------------------------------------
    # Berechnete Eigenschaften
    # ------------------------------------------------------------------

    @graph_ql_property
    def offerte_stunden(self) -> Decimal | None:
        """
        Berechnete Stunden-Anzahl aus der Offerte (nur STUNDEN-Position):
          offerte_kosten_wert(TRANSPORT_MONTAGE) / stundensatz(projekt.jahr)
        """
        if self.art.schluessel != "stunden":
            return None

        tm_kp = KostenPosition.filter(
            projekt=self.projekt, art__schluessel="transport_montage"
        ).first()
        if tm_kp is None or tm_kp.offerte_kosten_wert is None:
            return None

        stundensatz_liste = list(Stundensatz.filter(jahr=self.projekt.jahr))
        if not stundensatz_liste:
            return None

        satz: Decimal = stundensatz_liste[0].stundensatz.magnitude
        if not satz:
            return None
        offerte_tm: Decimal = tm_kp.offerte_kosten_wert.magnitude
        return (offerte_tm / satz).quantize(Decimal("0.01"))

    @staticmethod
    def _prozent_von(wert: Decimal | None, summe: Decimal | None) -> Decimal | None:
        if wert is None or not summe:
            return None
        return (wert / summe * 100).quantize(Decimal("0.01"))

    @graph_ql_property
    def offerte_kosten_wert_prozent(self) -> Decimal | None:
        """offerte_kosten_wert / offerte_summe * 100"""
        if self.offerte_kosten_wert is None:
            return None
        return self._prozent_von(
            self.offerte_kosten_wert.magnitude,
            self.projekt.offerte_summe.magnitude,
        )

    @graph_ql_property
    def wv_kosten_wert(self) -> Measurement | None:
        """
        Soll-WV-Wert der Position:
        - STUNDEN                 → offerte_stunden (gleicher Wert, Ausnahme)
        - TRANSPORT_MONTAGE       → offerte_kosten_wert (bleibt gleich, Ausnahme)
        - TRANSPORT_MONTAGE_FREMD → offerte_kosten_wert (bleibt gleich, Ausnahme)
        - APPARATE/KANAELE/ARMATUREN → Formel mit TM-Delta-Korrektur
        - alle anderen            → offerte_kosten_wert / offerte_summe * wv_summe
        """
        schluessel = self.art.schluessel

        if schluessel == "stunden":
            stunden = self.offerte_stunden
            return Measurement(Decimal(stunden), "h") if stunden is not None else None

        if schluessel in ("transport_montage", "transport_montage_fremd"):
            return self.offerte_kosten_wert

        if schluessel in _DREI_SCHLUSSEL:
            wert = self._soll_wv_drei_positionen()
            return Measurement(wert, "CHF") if wert is not None else None

        if self.offerte_kosten_wert is None:
            return None
        if self.projekt.wv_summe is None:
            return None
        offerte_summe: Decimal = self.projekt.offerte_summe.magnitude
        wv_summe: Decimal = self.projekt.wv_summe.magnitude
        if not offerte_summe:
            return None
        offerte_val: Decimal = self.offerte_kosten_wert.magnitude
        return Measurement(
            (offerte_val / offerte_summe * wv_summe).quantize(Decimal("0.01")), "CHF"
        )

    def _soll_wv_drei_positionen(self) -> Decimal | None:
        """
        WV-Berechnung für APPARATE, KANAELE_ROHRE, ARMATUREN.

        Da TRANSPORT_MONTAGE und TRANSPORT_MONTAGE_FREMD ihren Offerte-CHF-Wert
        unverändert in den WV übernehmen (Ausnahme laut Spec), steht weniger Budget
        für die drei Hauptkostenpositionen zur Verfügung. Der überschüssige Anteil
        (Delta) wird proportional anhand der Offerte-Anteile auf die drei verteilt.
        """
        if self.projekt.wv_summe is None:
            return None
        offerte_summe: Decimal = self.projekt.offerte_summe.magnitude
        wv_summe: Decimal = self.projekt.wv_summe.magnitude
        if not offerte_summe:
            return None

        def _offerte(schluessel: str) -> Decimal:
            kp = KostenPosition.filter(
                projekt=self.projekt, art__schluessel=schluessel
            ).first()
            if kp is None or kp.offerte_kosten_wert is None:
                return Decimal("0")
            return Decimal(kp.offerte_kosten_wert.magnitude)

        offerte_app = _offerte("apparate")
        offerte_kan = _offerte("kanaele_rohre")
        offerte_arm = _offerte("armaturen")
        offerte_tm = _offerte("transport_montage")
        offerte_tmf = _offerte("transport_montage_fremd")

        delta_tm = offerte_tm - (offerte_tm / offerte_summe * wv_summe)
        delta_tmf = offerte_tmf - (offerte_tmf / offerte_summe * wv_summe)

        summe_der_drei = (
            (offerte_app + offerte_kan + offerte_arm) / offerte_summe * wv_summe
        )
        if not summe_der_drei:
            return None

        schluessel = self.art.schluessel
        if schluessel == "apparate":
            offerte_i = offerte_app
        elif schluessel == "kanaele_rohre":
            offerte_i = offerte_kan
        else:
            offerte_i = offerte_arm

        tmp_position = offerte_i / offerte_summe * wv_summe
        wv_i = (
            tmp_position
            - delta_tm * (tmp_position / summe_der_drei)
            - delta_tmf * (tmp_position / summe_der_drei)
        )
        return Decimal(wv_i).quantize(Decimal("0.01"))

    @graph_ql_property
    def wv_kosten_wert_prozent(self) -> Decimal | None:
        """wv_kosten_wert / wv_summe * 100"""
        wv = self.wv_kosten_wert
        wv_summe = self.projekt.wv_summe
        return self._prozent_von(
            wv.magnitude if wv is not None else None,
            wv_summe.magnitude if wv_summe is not None else None,
        )
