from django.conf import settings


def test_installed_apps() -> None:
    assert "general_manager" in settings.INSTALLED_APPS
    assert "graphene_django" in settings.INSTALLED_APPS
    assert "daphne" in settings.INSTALLED_APPS
