"""Carga las sedes desde db/jsons/of/stadiums.json (idempotente)."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from tournament.models import Stadium

JSON_PATH = (
    Path(settings.BASE_DIR) / "db" / "jsons" / "of" / "stadiums.json"
)


def parse_utc_offset(raw: str) -> int:
    """Convierte un timezone de OF ("UTC-7") en un offset entero (-7)."""
    return int(raw.replace("UTC", "") or 0)


class Command(BaseCommand):
    help = "Carga las sedes desde of/stadiums.json de forma idempotente."

    def handle(self, *args, **options) -> None:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            stadiums = json.load(f)["stadiums"]

        created = 0
        for item in stadiums:
            _, was_created = Stadium.objects.update_or_create(
                name=item["name"],
                defaults={
                    "city": item["city"],
                    "country": item["cc"],
                    "utc_offset": parse_utc_offset(item["timezone"]),
                    "capacity": item.get("capacity"),
                    "coords": item.get("coords", ""),
                },
            )
            created += was_created

        self.stdout.write(self.style.SUCCESS(
            f"Sedes: {created} creadas (de {len(stadiums)})."
        ))
