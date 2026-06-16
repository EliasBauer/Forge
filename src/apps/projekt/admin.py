from django.contrib import admin

from apps.projekt.models import KostenPosition, Projekt


@admin.register(Projekt.Interface._model)  # type: ignore[misc]
class ProjektAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "auftragsnummer",
        "name",
        "projektleiter",
        "wv_summe",
        "auftrag_fertig",
    )
    list_filter = ("auftrag_fertig",)
    search_fields = ("name", "auftragsnummer")


@admin.register(KostenPosition.Interface._model)  # type: ignore[misc]
class KostenPositionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("projekt", "art", "offerte_kosten_wert")
    list_filter = ("art",)
    raw_id_fields = ("projekt",)
