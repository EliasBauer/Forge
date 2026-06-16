import importlib

from django.apps import AppConfig


class BexioConfig(AppConfig):
    name = "apps.bexio"

    def ready(self) -> None:
        importlib.import_module("apps.bexio.models")
        importlib.import_module("apps.bexio.calculation_manager")
