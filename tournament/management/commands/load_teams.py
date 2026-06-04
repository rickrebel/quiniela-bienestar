"""Carga las selecciones combinando OF (base) y FD (enriquecido).

OF aporta nombre, banderas, grupo y confederación; un JSON manual aporta
``name_es``; FD aporta ``fd_id``, ``short_name`` y ``crest``. El join
OF↔FD es por ``fifa_code`` (OF) == ``tla`` (FD), salvo Uruguay (URU→URY).
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from tournament.models import Team

JSONS = Path(settings.BASE_DIR) / "db" / "jsons"
OF_PATH = JSONS / "of" / "teams.json"
FD_PATH = JSONS / "fd" / "teams.json"
NAMES_ES_PATH = JSONS / "manual" / "team_names_es.json"

# Único código OF cuyo tla difiere en FD.
FIFA_TO_TLA = {"URU": "URY"}

# Fútbol separa al Reino Unido por naciones; sus banderas usan una secuencia
# distinta (tag sequence) que no se deriva del emoji, así que van a mano.
FLAG_OVERRIDES = {
    "ENG": "gb-eng", "WAL": "gb-wls",
    "SCO": "gb-sct", "NIR": "gb-nir",
}


def derive_flag_code(flag_icon: str) -> str:
    """Convierte el emoji de bandera (2 regional indicators) a ISO alpha-2."""
    base = 0x1F1E6  # 🇦
    chars = [c for c in flag_icon if base <= ord(c) <= 0x1F1FF]
    if len(chars) != 2:
        return ""
    return "".join(chr(ord(c) - base + ord("a")) for c in chars)


class Command(BaseCommand):
    help = "Carga selecciones desde OF y las enriquece con FD."

    def handle(self, *args, **options) -> None:
        with open(OF_PATH, encoding="utf-8") as f:
            of_teams = json.load(f)
        with open(NAMES_ES_PATH, encoding="utf-8") as f:
            names_es = json.load(f)

        fd_by_tla: dict[str, dict] = {}
        if FD_PATH.exists():
            with open(FD_PATH, encoding="utf-8") as f:
                for t in json.load(f).get("teams", []):
                    fd_by_tla[t["tla"]] = t

        created = enriched = 0
        for item in of_teams:
            fifa = item["fifa_code"]
            flag_icon = item.get("flag_icon", "")
            defaults = {
                "name": item["name"],
                "name_es": names_es.get(fifa, item["name"]),
                "flag_icon": flag_icon,
                "flag_unicode": item.get("flag_unicode", ""),
                "flag_code": FLAG_OVERRIDES.get(fifa) or derive_flag_code(
                    flag_icon
                ),
                "group_name": item["group"],
                "confederation": item["confed"],
                "raw_of": item,
            }

            fd = fd_by_tla.get(FIFA_TO_TLA.get(fifa, fifa))
            if fd:
                defaults.update({
                    "fd_id": fd["id"],
                    "short_name": fd.get("shortName") or "",
                    "crest": fd.get("crest") or "",
                    "raw_fd": fd,
                })
                enriched += 1

            _, was_created = Team.objects.update_or_create(
                fifa_code=fifa, defaults=defaults
            )
            created += was_created

        self.stdout.write(self.style.SUCCESS(
            f"Selecciones: {created} creadas (de {len(of_teams)}); "
            f"{enriched} enriquecidas con FD."
        ))
