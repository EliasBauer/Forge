import importlib

from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    name = "apps.authentication"

    def ready(self) -> None:
        importlib.import_module("apps.authentication.permission")
        importlib.import_module("apps.authentication.managers")
