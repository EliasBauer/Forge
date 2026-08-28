from __future__ import annotations

from typing import Any

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


@pytest.fixture(autouse=True)
def _seed_projekt_status(db: None) -> None:
    """
    Sorgt dafür, dass die drei ProjektStatus-Einträge (Offen/In Arbeit/Fertig)
    vor jedem Test existieren.

    Projekt.create() braucht ProjektStatus.filter(name="Offen") für seinen
    Default. ReadOnlyInterface synct _data zwar beim App-Start, aber nicht
    zuverlässig gegen die pytest-Testdatenbank — aus demselben Grund seeden
    die Kostenart-Tests in diesem Projekt ebenfalls manuell (siehe
    test_kostenart.py, test_kosten_position.py).
    """
    from apps.projekt.models import ProjektStatus

    model: Any = ProjektStatus.Interface._model
    model.objects.bulk_create(
        [model(**item) for item in ProjektStatus._data],
        ignore_conflicts=True,
    )
