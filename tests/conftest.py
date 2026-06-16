from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


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
