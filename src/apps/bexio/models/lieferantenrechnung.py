from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models
from general_manager import AdditiveManagerPermission, DatabaseInterface, GeneralManager
from general_manager.api.property import graph_ql_property

if TYPE_CHECKING:
    from apps.bexio.models.konto import Konto


class Lieferantenrechnung(GeneralManager):
    """Spiegel der Bexio-Lieferantenrechnungen. Bexio gewinnt immer. Ein Eintrag pro Zeilenposition."""  # noqa: E501

    id: int
    bexio_id: uuid.UUID
    bexio_zeilen_id: uuid.UUID
    dokument_nr: str
    titel: str
    richtiger_titel: str
    status: str
    rechnungsdatum: date
    faelligkeitsdatum: date | None
    lieferant_id: int
    firmenname: str
    verkaeufer_ref: str | None
    waehrung_code: str
    rechnungsbetrag: Decimal
    ausstehender_betrag: Decimal
    ueberfaellig: bool
    bexio_erstellt_am: datetime
    position: int
    betrag: Decimal
    zeilen_titel: str | None
    steuer_berechnet: Decimal
    buchungskonto: Konto | None

    class Interface(DatabaseInterface):
        bexio_id = models.UUIDField()
        bexio_zeilen_id = models.UUIDField(unique=True, default=uuid.uuid4)
        dokument_nr = models.CharField(max_length=20)
        titel = models.CharField(max_length=100)
        richtiger_titel = models.CharField(max_length=100)
        status = models.CharField(max_length=20)
        rechnungsdatum = models.DateField()
        faelligkeitsdatum = models.DateField(null=True, blank=True)
        lieferant_id = models.IntegerField()
        firmenname = models.CharField(max_length=200)
        verkaeufer_ref = models.CharField(max_length=100, null=True, blank=True)
        waehrung_code = models.CharField(max_length=3)
        rechnungsbetrag = models.DecimalField(max_digits=12, decimal_places=2)
        ausstehender_betrag = models.DecimalField(max_digits=12, decimal_places=2)
        ueberfaellig = models.BooleanField(default=False)
        bexio_erstellt_am = models.DateTimeField()
        position = models.IntegerField(default=0)
        betrag = models.DecimalField(max_digits=12, decimal_places=2, default=0)
        zeilen_titel = models.CharField(max_length=200, null=True, blank=True)
        steuer_berechnet = models.DecimalField(
            max_digits=12, decimal_places=2, default=0
        )
        buchungskonto = models.ForeignKey(
            "bexio.Konto",
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
            related_name="lieferantenrechnungen",
        )

        class Meta:
            verbose_name = "Lieferantenrechnung"
            verbose_name_plural = "Lieferantenrechnungen"
            ordering = ["-rechnungsdatum", "position"]

    class Permission(AdditiveManagerPermission):
        __read__ = ["isAuthenticated"]
        __create__ = ["isAdmin"]
        __update__ = ["isAdmin"]
        __delete__ = ["isAdmin"]

    # ------------------------------------------------------------------
    # Berechnete Eigenschaften
    # ------------------------------------------------------------------

    @graph_ql_property
    def netto_betrag(self) -> Decimal:
        return self.betrag - self.steuer_berechnet
