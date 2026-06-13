"""Carga dump_full.json en prod desconectando la señal
create_stage_users (que duplicaría StageUser durante el loaddata) y
resetea las secuencias de Postgres al final. Uso:
    python load_prod.py
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.apps import apps
from django.core.management import call_command
from django.core.management.color import no_style
from django.db import connection
from django.db.models.signals import post_save

from pool import signals
from pool.models import User

post_save.disconnect(signals.create_stage_users, sender=User)
call_command("loaddata", "dump_full.json")

models = []
for app in ("pool", "tournament"):
    models.extend(apps.get_app_config(app).get_models())
reset_sql = connection.ops.sequence_reset_sql(no_style(), models)
with connection.cursor() as cursor:
    for stmt in reset_sql:
        cursor.execute(stmt)
print(f"Secuencias reseteadas: {len(reset_sql)} sentencias")
