import importlib

from django.apps import AppConfig


class StundenConfig(AppConfig):
    name = "apps.stunden"

    def ready(self) -> None:
        importlib.import_module("apps.stunden.models")
        importlib.import_module("apps.stunden.calculation_manager")
