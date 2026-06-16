from django.contrib import admin

from apps.stunden.models import Stundensatz


@admin.register(Stundensatz.Interface._model)  # type: ignore[misc]
class StundensatzAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("jahr", "stundensatz")
    ordering = ("-jahr",)
