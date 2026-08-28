from __future__ import annotations

from typing import Any

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def backfill_projekt_status(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    ProjektStatusModel: Any = apps.get_model("projekt", "ProjektStatus")
    ProjektModel: Any = apps.get_model("projekt", "Projekt")

    offen, _ = ProjektStatusModel.objects.get_or_create(name="Offen")
    in_arbeit, _ = ProjektStatusModel.objects.get_or_create(name="In Arbeit")
    fertig, _ = ProjektStatusModel.objects.get_or_create(name="Fertig")

    ProjektModel.objects.filter(auftrag_fertig=True).update(projekt_status=fertig)
    ProjektModel.objects.filter(auftrag_fertig=False).update(projekt_status=in_arbeit)


def noop_reverse(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Kein Rückweg nötig — auftrag_fertig existiert in dieser Migration noch."""


class Migration(migrations.Migration):
    dependencies = [
        ("projekt", "0007_projekt_projekt_status"),
    ]

    operations = [
        migrations.RunPython(backfill_projekt_status, noop_reverse),
    ]
