from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path

from apps.bexio.models import Konto, Lieferantenrechnung


@admin.register(Konto.Interface._model)  # type: ignore[misc]
class KontoAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    change_list_template = "admin/bexio/konto/change_list.html"

    list_display = (
        "bexio_id",
        "account_no",
        "name",
        "account_type",
        "is_active",
        "is_locked",
    )
    list_filter = ("is_active", "is_locked", "account_type")
    search_fields = ("account_no", "name")
    readonly_fields = [
        f.name
        for f in Konto.Interface._model._meta.get_fields()  # type: ignore[misc]
        if hasattr(f, "name")
    ]
    ordering = ("account_no",)

    def get_urls(self) -> list:  # type: ignore[type-arg]
        urls = super().get_urls()
        custom = [
            path(
                "full-sync/",
                self.admin_site.admin_view(self.full_sync_view),
                name="bexio_konto_full_sync",
            ),
            path(
                "sync/",
                self.admin_site.admin_view(self.sync_view),
                name="bexio_konto_sync",
            ),
        ]
        return custom + urls

    def full_sync_view(self, request: HttpRequest) -> HttpResponseRedirect:
        from apps.bexio.sync import full_sync_konten

        try:
            count = full_sync_konten()
            self.message_user(
                request,
                f"Vollständige Aktualisierung abgeschlossen: {count} Konten geladen.",
                level=messages.SUCCESS,
            )
        except Exception as exc:
            self.message_user(request, f"Fehler: {exc}", level=messages.ERROR)
        return HttpResponseRedirect("../")

    def sync_view(self, request: HttpRequest) -> HttpResponseRedirect:
        from apps.bexio.sync import sync_konten

        try:
            count = sync_konten()
            self.message_user(
                request,
                f"Sync abgeschlossen: {count} Konten verarbeitet.",
                level=messages.SUCCESS,
            )
        except Exception as exc:
            self.message_user(request, f"Fehler: {exc}", level=messages.ERROR)
        return HttpResponseRedirect("../")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(Lieferantenrechnung.Interface._model)  # type: ignore[misc]
class LieferantenrechnungAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    change_list_template = "admin/bexio/lieferantenrechnung/change_list.html"

    list_display = (
        "bexio_id",
        "dokument_nr",
        "richtiger_titel",
        "status",
        "rechnungsdatum",
        "firmenname",
        "rechnungsbetrag",
        "position",
        "betrag",
        "buchungskonto",
        "ueberfaellig",
    )
    list_filter = ("status", "ueberfaellig", "waehrung_code")
    search_fields = ("titel", "richtiger_titel", "dokument_nr", "firmenname")
    readonly_fields = [
        f.name
        for f in Lieferantenrechnung.Interface._model._meta.get_fields()  # type: ignore[misc]
        if hasattr(f, "name")
    ]
    ordering = ("-rechnungsdatum",)

    def get_urls(self) -> list:  # type: ignore[type-arg]
        urls = super().get_urls()
        custom = [
            path(
                "full-sync/",
                self.admin_site.admin_view(self.full_sync_view),
                name="bexio_lieferantenrechnung_full_sync",
            ),
            path(
                "sync/",
                self.admin_site.admin_view(self.sync_view),
                name="bexio_lieferantenrechnung_sync",
            ),
        ]
        return custom + urls

    def full_sync_view(self, request: HttpRequest) -> HttpResponseRedirect:
        from apps.bexio.sync import full_sync_lieferantenrechnungen

        try:
            count = full_sync_lieferantenrechnungen()
            self.message_user(
                request,
                f"Vollständige Aktualisierung abgeschlossen: {count} Einträge geladen.",
                level=messages.SUCCESS,
            )
        except Exception as exc:
            self.message_user(request, f"Fehler: {exc}", level=messages.ERROR)
        return HttpResponseRedirect("../")

    def sync_view(self, request: HttpRequest) -> HttpResponseRedirect:
        from apps.bexio.sync import sync_lieferantenrechnungen

        try:
            count = sync_lieferantenrechnungen()
            self.message_user(
                request,
                f"Sync abgeschlossen: {count} Einträge verarbeitet.",
                level=messages.SUCCESS,
            )
        except Exception as exc:
            self.message_user(request, f"Fehler: {exc}", level=messages.ERROR)
        return HttpResponseRedirect("../")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False
