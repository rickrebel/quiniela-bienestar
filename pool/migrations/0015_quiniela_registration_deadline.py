from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations, models

# Cierre por defecto para las quinielas ya existentes: fin del 24 de
# junio de 2026 (hora de la Ciudad de México). Al ser una fecha pasada,
# deja los registros cerrados en cuanto se aplica la migración.
DEFAULT_DEADLINE = datetime(
    2026, 6, 24, 23, 59, 59, tzinfo=ZoneInfo("America/Mexico_City"))


def set_default_deadline(apps, schema_editor):
    Quiniela = apps.get_model("pool", "Quiniela")
    Quiniela.objects.update(registration_deadline=DEFAULT_DEADLINE)


def clear_deadline(apps, schema_editor):
    Quiniela = apps.get_model("pool", "Quiniela")
    Quiniela.objects.update(registration_deadline=None)


class Migration(migrations.Migration):

    dependencies = [
        ('pool', '0014_remove_scoresnapshot_position'),
    ]

    operations = [
        migrations.AddField(
            model_name='quiniela',
            name='registration_deadline',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    'Después de esta fecha no se admiten altas nuevas. '
                    'Vacío = registro abierto sin límite.'
                ),
            ),
        ),
        migrations.RunPython(set_default_deadline, clear_deadline),
    ]
