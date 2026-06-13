"""Respaldo de datos vía ORM, equivalente a dumpdata pero sin
server-side cursors (que fallan contra el RDS). Uso:
    python dump_all.py salida.json
"""
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.apps import apps
from django.core import serializers

EXCLUDE = {"contenttypes.contenttype", "auth.permission",
           "sessions.session", "admin.logentry"}


def main(out_path: str) -> None:
    objs = []
    for model in apps.get_models():
        label = model._meta.label_lower
        if label in EXCLUDE:
            continue
        rows = list(model.objects.all())
        print(f"{label}: {len(rows)}")
        objs.extend(rows)
    with open(out_path, "w", encoding="utf-8") as fh:
        serializers.serialize("json", objs, indent=2, stream=fh,
                              use_natural_foreign_keys=True)
    print(f"Total: {len(objs)} objetos -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1])
