from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_django_cache() -> None:
    """
    Leert den Django-Cache vor jedem Test.

    Nötig weil @graph_ql_property die berechneten Werte per django_cache
    speichert. Ohne Leeren würden Cache-Einträge aus früheren Tests
    falsche Werte an Folgetests zurückliefern.
    """
    from django.core.cache import cache

    cache.clear()
