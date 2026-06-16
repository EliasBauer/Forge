# Signals deaktiviert: KostenPositionen werden nicht mehr automatisch beim Anlegen
# eines Projekts oder einer Kostenart erstellt. Das Frontend baut die Tabelle
# direkt aus KOSTEN_REIHENFOLGE auf und zeigt "–" wenn keine DB-Position existiert.
#
# from __future__ import annotations
#
# from typing import Any
#
# from django.db.models.signals import post_save
# from django.dispatch import receiver
#
# from apps.projekt.models import Kostenart, KostenPosition, Projekt
#
# _ProjektModel: Any = Projekt.Interface._model  # type: ignore[misc]
# _KostenartModel: Any = Kostenart.Interface._model  # type: ignore[misc]
#
#
# @receiver(post_save, sender=_ProjektModel)
# def create_kosten_positionen_fuer_projekt(
#     sender: type, instance: Any, created: bool, **kwargs: object
# ) -> None:
#     if not created:
#         return
#     for art in Kostenart.all():
#         if KostenPosition.filter(projekt_id=instance.id, art_id=art.id):
#             continue
#         KostenPosition.create(
#             creator_id=None,
#             ignore_permission=True,
#             projekt_id=instance.id,
#             art_id=art.id,
#         )
#
#
# @receiver(post_save, sender=_KostenartModel)
# def create_kosten_positionen_fuer_kostenart(
#     sender: type, instance: Any, created: bool, **kwargs: object
# ) -> None:
#     if not created:
#         return
#     for projekt in Projekt.all():
#         if KostenPosition.filter(projekt_id=projekt.id, art_id=instance.id):
#             continue
#         KostenPosition.create(
#             creator_id=None,
#             ignore_permission=True,
#             projekt_id=projekt.id,
#             art_id=instance.id,
#         )
