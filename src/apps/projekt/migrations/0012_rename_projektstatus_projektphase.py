from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("projekt", "0011_alter_historicalkostenposition_art_and_more"),
    ]

    operations = [
        migrations.RenameModel(old_name="ProjektStatus", new_name="ProjektPhase"),
        migrations.RenameModel(
            old_name="HistoricalProjektStatus", new_name="HistoricalProjektPhase"
        ),
        migrations.AlterModelTable(name="projektphase", table="projekt_projektphase"),
        migrations.AlterModelOptions(
            name="projektphase",
            options={
                "ordering": ["id"],
                "verbose_name": "Projekt-Phase",
                "verbose_name_plural": "Projekt-Phasen",
            },
        ),
        migrations.AlterModelOptions(
            name="historicalprojektphase",
            options={
                "get_latest_by": ("history_date", "history_id"),
                "ordering": ("-history_date", "-history_id"),
                "verbose_name": "historical Projekt-Phase",
                "verbose_name_plural": "historical Projekt-Phasen",
            },
        ),
        migrations.RenameField(
            model_name="projekt", old_name="projekt_status", new_name="projekt_phase"
        ),
        migrations.RenameField(
            model_name="historicalprojekt",
            old_name="projekt_status",
            new_name="projekt_phase",
        ),
    ]
