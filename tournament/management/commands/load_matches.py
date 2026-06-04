"""Carga los partidos desde OF y mapea su fd_id contra el snapshot FD.

Estructura, sedes y placeholders salen de OF (worldcup.json). El fd_id se
resuelve cruzando por (datetime UTC + tla del local), con override
URU→URY. of_number: en eliminatorias es el ``num`` de OF (73..104); en
grupos OF no trae número, así que se asignan 1..72 por orden cronológico.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from tournament.models import Match, Stadium, Stage, Team

JSONS = Path(settings.BASE_DIR) / "db" / "jsons"
OF_PATH = JSONS / "of" / "worldcup.json"
FD_PATH = JSONS / "fd" / "matches.json"
OF_TEAMS_PATH = JSONS / "of" / "teams.json"

FIFA_TO_TLA = {"URU": "URY"}

# Prefijo/igualdad de OF round -> clave de Stage.
STAGE_BY_ROUND = {
    "Round of 32": Stage.LAST_32,
    "Round of 16": Stage.LAST_16,
    "Quarter-final": Stage.QUARTER_FINALS,
    "Semi-final": Stage.SEMI_FINALS,
    "Match for third place": Stage.FINAL,
    "Final": Stage.FINAL,
}


def of_utc(date_str: str, time_str: str) -> datetime:
    """Combina fecha + hora local de OF ("13:00 UTC-6") en datetime UTC."""
    hhmm, offset = time_str.split(" ")
    hours = int(offset.replace("UTC", "") or 0)
    naive = datetime.strptime(f"{date_str} {hhmm}", "%Y-%m-%d %H:%M")
    aware = naive.replace(tzinfo=timezone(timedelta(hours=hours)))
    return aware.astimezone(timezone.utc)


def stage_key(round_name: str) -> str:
    """Mapea el ``round`` de OF a una clave de Stage (6 fases)."""
    if round_name.startswith("Matchday"):
        return Stage.GROUP_STAGE
    return STAGE_BY_ROUND[round_name]


class Command(BaseCommand):
    help = "Carga partidos desde OF y mapea fd_id contra el snapshot FD."

    def handle(self, *args, **options) -> None:
        with open(OF_PATH, encoding="utf-8") as f:
            of_matches = json.load(f)["matches"]
        with open(OF_TEAMS_PATH, encoding="utf-8") as f:
            fifa_by_name = {t["name"]: t["fifa_code"] for t in json.load(f)}

        fd_index = self._build_fd_index()
        stages = {s.key: s for s in Stage.objects.all()}
        teams = {t.name: t for t in Team.objects.all()}
        stadiums = {s.city: s for s in Stadium.objects.all()}

        self._assign_of_numbers(of_matches)

        created = mapped = 0
        for item in of_matches:
            dt = of_utc(item["date"], item["time"])
            is_group = "num" not in item
            home_name, away_name = item["team1"], item["team2"]

            home_tla = FIFA_TO_TLA.get(
                fifa_by_name.get(home_name), fifa_by_name.get(home_name)
            )
            fd = fd_index.get((dt, home_tla)) or fd_index.get((dt, None))

            defaults = {
                "datetime": dt,
                "stage": stages[stage_key(item["round"])],
                "stadium": stadiums[item["ground"]],
                "home_team": teams.get(home_name) if is_group else None,
                "away_team": teams.get(away_name) if is_group else None,
                "home_placeholder": "" if is_group else home_name,
                "away_placeholder": "" if is_group else away_name,
                "status": fd["status"] if fd else "SCHEDULED",
                "fd_id": fd["id"] if fd else None,
            }
            mapped += fd is not None

            _, was_created = Match.objects.update_or_create(
                of_number=item["of_number"], defaults=defaults
            )
            created += was_created

        self.stdout.write(self.style.SUCCESS(
            f"Partidos: {created} creados (de {len(of_matches)}); "
            f"{mapped} mapeados a fd_id."
        ))

    def _build_fd_index(self) -> dict:
        """Indexa el snapshot FD por (datetime, tla_local) y (datetime, None).

        La clave (datetime, None) permite cruzar eliminatorias, donde FD
        aún no tiene equipos y solo la hora identifica el partido.
        """
        index: dict = {}
        if not FD_PATH.exists():
            return index
        with open(FD_PATH, encoding="utf-8") as f:
            for m in json.load(f).get("matches", []):
                dt = datetime.strptime(
                    m["utcDate"], "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
                tla = (m.get("homeTeam") or {}).get("tla")
                index[(dt, tla)] = m
                index.setdefault((dt, None), m)
        return index

    @staticmethod
    def _assign_of_numbers(of_matches: list[dict]) -> None:
        """Fija ``of_number`` en cada item (in-place).

        OF trae ``num`` solo de dieciseisavos a semifinales (73..102). El
        partido por el tercer lugar y la final NO traen ``num``: se fijan
        a 103 y 104 (hardcode acordado). Los grupos (``Matchday*``) se
        numeran 1..72 por orden cronológico (desempate determinista).
        """
        group_items = [
            m for m in of_matches if m["round"].startswith("Matchday")
        ]
        group_items.sort(
            key=lambda m: (m["date"], m["time"], m["group"], m["team1"])
        )
        for i, item in enumerate(group_items, start=1):
            item["of_number"] = i
        for item in of_matches:
            if "num" in item:
                item["of_number"] = item["num"]
            elif item["round"] == "Match for third place":
                item["of_number"] = Match.THIRD_PLACE_NUMBER
            elif item["round"] == "Final":
                item["of_number"] = Match.FINAL_NUMBER
