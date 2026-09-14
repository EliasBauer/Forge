"""Demo-Projekte für die lokale Entwicklung.

Wird von ``setup_dev_data`` aufgerufen. Die Auftragsnummern folgen dem
betrieblichen Schema ``JJJJ.NNNN`` (Jahr plus fortlaufende Nummer). Die
Bexio-Dev-Fixtures (``apps.bexio.services``) tragen dieselben Nummern als
Rechnungstitel, damit in der Projektübersicht Ist-Kosten erscheinen.

Idempotent: Projekte werden über die Auftragsnummer, Kostenpositionen über
(Projekt, Kostenart) und Stundensätze über das Jahr wiedergefunden.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from general_manager.measurement import Measurement

from apps.projekt.models import Kostenart, KostenPosition, Projekt, ProjektPhase
from apps.stunden.models import Stundensatz

DEV_STUNDENSAETZE: dict[int, Decimal] = {
    2024: Decimal("85"),
    2025: Decimal("87"),
    2026: Decimal("89"),
}

_STUNDEN = "stunden"


@dataclass(frozen=True)
class DevProjekt:
    auftragsnummer: str
    name: str
    phase: str
    projektleiter: str
    wv_faktor: Decimal | None
    positionen: dict[str, Decimal]

    @property
    def jahr(self) -> int:
        return int(self.auftragsnummer.split(".")[0])

    @property
    def offerte_summe(self) -> Decimal:
        return sum(
            (
                wert
                for schluessel, wert in self.positionen.items()
                if schluessel != _STUNDEN
            ),
            Decimal("0"),
        )

    @property
    def wv_summe(self) -> Decimal | None:
        if self.wv_faktor is None:
            return None
        return (self.offerte_summe * self.wv_faktor).quantize(Decimal("0.01"))


def _p(
    auftragsnummer: str,
    name: str,
    phase: str,
    projektleiter: str,
    wv_faktor: str | None,
    **positionen: int,
) -> DevProjekt:
    return DevProjekt(
        auftragsnummer=auftragsnummer,
        name=name,
        phase=phase,
        projektleiter=projektleiter,
        wv_faktor=Decimal(wv_faktor) if wv_faktor is not None else None,
        positionen={k: Decimal(v) for k, v in positionen.items()},
    )


DEV_PROJEKTE: list[DevProjekt] = [
    _p(
        "2024.0168",
        "MFH Rosenweg, Uster",
        "Fertig",
        "simon",
        "0.94",
        apparate=38000,
        kanaele_rohre=27500,
        armaturen=9800,
        regulierung=6200,
        schaltschrank=7400,
        transport_montage=24000,
        isolation=5600,
        planung=4200,
        stunden=0,
    ),
    _p(
        "2024.0171",
        "Schulhaus Bergstrasse, Sanierung",
        "Fertig",
        "simon",
        "0.97",
        apparate=62000,
        kanaele_rohre=41000,
        armaturen=14500,
        regulierung=9800,
        schaltschrank=11200,
        transport_montage=38000,
        isolation=8900,
        planung=7500,
        stunden=0,
    ),
    _p(
        "2024.0185",
        "Produktionshalle Keller AG",
        "Fertig",
        "kalle",
        "1.02",
        apparate=24000,
        kanaele_rohre=18500,
        armaturen=6200,
        regulierung=3900,
        transport_montage=15600,
        isolation=3100,
        planung=2800,
        stunden=0,
    ),
    _p(
        "2025.0012",
        "Alterszentrum Sonnenhof, Erweiterung",
        "Fertig",
        "simon",
        "0.95",
        apparate=88000,
        kanaele_rohre=56000,
        armaturen=19500,
        regulierung=12400,
        schaltschrank=14800,
        transport_montage=52000,
        isolation=11200,
        planung=9600,
        stunden=0,
    ),
    _p(
        "2025.0047",
        "Bürogebäude Technopark, Etage 3",
        "In Arbeit",
        "simon",
        "0.98",
        apparate=31000,
        kanaele_rohre=22000,
        armaturen=8100,
        regulierung=5400,
        schaltschrank=6300,
        transport_montage=19500,
        isolation=4700,
        planung=3900,
        stunden=0,
    ),
    _p(
        "2025.0091",
        "Turnhalle Gemeinde Wil",
        "In Arbeit",
        "kalle",
        "0.96",
        apparate=45000,
        kanaele_rohre=33000,
        armaturen=11800,
        regulierung=7600,
        schaltschrank=9100,
        transport_montage=28000,
        isolation=6500,
        planung=5200,
        stunden=0,
    ),
    _p(
        "2025.0133",
        "Laborgebäude Campus Nord",
        "In Arbeit",
        "kalle",
        "0.93",
        apparate=120000,
        kanaele_rohre=74000,
        armaturen=26000,
        regulierung=18500,
        schaltschrank=21000,
        transport_montage=69000,
        isolation=15800,
        planung=13400,
        stunden=0,
    ),
    _p(
        "2026.0008",
        "EFH Seestrasse, Komfortlüftung",
        "In Arbeit",
        "simon",
        "1.00",
        apparate=14500,
        kanaele_rohre=9800,
        armaturen=3200,
        regulierung=2100,
        transport_montage=8400,
        isolation=1900,
        planung=1600,
        stunden=0,
    ),
    _p(
        "2026.0021",
        "Hotel Alpenblick, Küchenabluft",
        "Offen",
        "simon",
        None,
        apparate=27000,
        kanaele_rohre=16500,
        armaturen=5900,
        regulierung=3800,
        schaltschrank=4600,
        transport_montage=14200,
        isolation=3300,
        planung=2900,
        stunden=0,
    ),
    _p(
        "2026.0034",
        "Kita Sonnenschein, Neubau",
        "Offen",
        "kalle",
        None,
        apparate=19800,
        kanaele_rohre=13400,
        armaturen=4700,
        regulierung=3100,
        schaltschrank=3800,
        transport_montage=11600,
        isolation=2600,
        planung=2300,
        stunden=0,
    ),
]

Log = Callable[[str], None]


def seed_dev_stundensaetze(log: Log) -> None:
    for jahr, satz in DEV_STUNDENSAETZE.items():
        wert = Measurement(satz, "CHF")
        vorhanden = Stundensatz.filter(jahr=jahr).first()
        if vorhanden is None:
            Stundensatz.create(
                creator_id=None, ignore_permission=True, jahr=jahr, stundensatz=wert
            )
            log(f"Stundensatz {jahr}: angelegt")
        else:
            vorhanden.update(creator_id=None, ignore_permission=True, stundensatz=wert)
            log(f"Stundensatz {jahr}: aktualisiert")


def _projektleiter_id(username: str) -> str:
    return str(User.objects.get(username=username).pk)


def _upsert_projekt(spec: DevProjekt) -> tuple[Projekt, bool]:
    felder: dict[str, Any] = {
        "name": spec.name,
        "jahr": spec.jahr,
        "projektleiter": _projektleiter_id(spec.projektleiter),
        "offerte_summe": Measurement(spec.offerte_summe, "CHF"),
        "wv_summe": (
            Measurement(spec.wv_summe, "CHF") if spec.wv_summe is not None else None
        ),
        "projekt_phase": ProjektPhase.get(name=spec.phase),
    }
    projekt = Projekt.filter(auftragsnummer=spec.auftragsnummer).first()
    if projekt is None:
        projekt = Projekt.create(
            creator_id=None,
            ignore_permission=True,
            auftragsnummer=spec.auftragsnummer,
            **felder,
        )
        return projekt, True
    projekt.update(creator_id=None, ignore_permission=True, **felder)
    return projekt, False


def _upsert_positionen(projekt: Projekt, spec: DevProjekt) -> None:
    for schluessel, wert in spec.positionen.items():
        art = Kostenart.get(schluessel=schluessel)
        # STUNDEN trägt keinen CHF-Wert; er wird aus TRANSPORT_MONTAGE berechnet.
        offerte = None if schluessel == _STUNDEN else Measurement(wert, "CHF")
        position = KostenPosition.filter(projekt=projekt, art=art).first()
        if position is None:
            KostenPosition.create(
                creator_id=None,
                ignore_permission=True,
                projekt_id=projekt.id,
                art_id=art.id,
                offerte_kosten_wert=offerte,
            )
        else:
            position.update(
                creator_id=None, ignore_permission=True, offerte_kosten_wert=offerte
            )


def seed_dev_projekte(log: Log) -> None:
    for spec in DEV_PROJEKTE:
        projekt, created = _upsert_projekt(spec)
        _upsert_positionen(projekt, spec)
        marker = "angelegt" if created else "aktualisiert"
        log(f"Projekt {spec.auftragsnummer} '{spec.name}': {marker}")
