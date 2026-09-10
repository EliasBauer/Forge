import importlib

from django.apps import AppConfig


class ProjektConfig(AppConfig):
    name = "apps.projekt"

    def ready(self) -> None:
        importlib.import_module("apps.projekt.models")
        importlib.import_module("apps.projekt.calculation_manager")
        from apps.projekt.models.projekt import _register_graphql_capabilities

        _register_graphql_capabilities()
