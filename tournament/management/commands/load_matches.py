"""Carga los partidos desde OF y mapea su fd_id contra el snapshot FD.

Estructura, sedes y placeholders salen de OF (worldcup.json). El fd_id se
resuelve cruzando por (datetime UTC + tla del local), con override
URU→URY. of_number: en eliminatorias es el ``num`` de OF (73..104); en
grupos OF no trae número, así que se asignan 1..72 por orden cronológico.
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from tournament.models import Match, Stadium, Stage, Team
from tournament.services.group_rounds import round_by_match

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

# Etiqueta legible por ronda; se numera por posición (p. ej. "Cuartos 3").
# OJO falso amigo: Round of 32 = dieciseisavos, Round of 16 = octavos.
ROUND_NAME_ES = {
    "Round of 32": "Dieciseisavos",
    "Round of 16": "Octavos",
    "Quarter-final": "Cuartos",
    "Semi-final": "Semifinal",
}


def of_utc(date_str: str, time_str: str) -> datetime:
    """Combina fecha + hora local de OF ("13:00 UTC-6") en datetime UTC."""
    hhmm, offset = time_str.split(" ")
    hours = int(offset.replace("UTC", "") or 0)
    naive = datetime.strptime(f"{date_str} {hhmm}", "%Y-%m-%d %H:%M")
    aware = naive.replace(tzinfo=timezone(timedelta(hours=hours)))
    return aware.astimezone(timezone.utc)


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
        self._assign_names(of_matches)

        created = mapped = 0
        for item in of_matches:
            dt = of_utc(item["date"], item["time"])
            # No por "num": tercer lugar y final tampoco lo traen y NO son
            # grupos; se distinguen por la ronda.
            is_group = item["round"].startswith("Matchday")
            home_name, away_name = item["team1"], item["team2"]

            home_tla = FIFA_TO_TLA.get(
                fifa_by_name.get(home_name), fifa_by_name.get(home_name)
            )
            fd = fd_index.get((dt, home_tla)) or fd_index.get((dt, None))

            # Los de grupo van provisional a SUBGROUP_1; la 2.ª pasada
            # (_assign_subgroup_rounds) los reparte por jornada.
            stage = (stages["SUBGROUP_1"] if is_group
                     else stages[STAGE_BY_ROUND[item["round"]]])

            defaults = {
                "datetime": dt,
                "stage": stage,
                "stadium": stadiums[item["ground"]],
                "home_team": teams.get(home_name) if is_group else None,
                "away_team": teams.get(away_name) if is_group else None,
                "home_placeholder": "" if is_group else home_name,
                "away_placeholder": "" if is_group else away_name,
                "name": item["name"],
                "status": fd["status"] if fd else "SCHEDULED",
                "fd_id": fd["id"] if fd else None,
            }
            mapped += fd is not None

            _, was_created = Match.objects.update_or_create(
                of_number=item["of_number"], defaults=defaults
            )
            created += was_created

        moved = self._assign_subgroup_rounds(stages)

        self.stdout.write(self.style.SUCCESS(
            f"Partidos: {created} creados (de {len(of_matches)}); "
            f"{mapped} mapeados a fd_id; {moved} repartidos por jornada."
        ))

    @staticmethod
    def _assign_subgroup_rounds(stages: dict) -> int:
        """Reparte los partidos de grupo en SUBGROUP_1/2/3 por jornada.

        Segunda pasada: ``round_by_match`` necesita los 6 partidos de cada
        grupo ya persistidos (los ordena por ``datetime`` y los parte en
        pares), así que la ronda no puede resolverse al crearlos. Devuelve
        cuántos partidos cambiaron de sub-fase.
        """
        subgroup = {
            1: stages["SUBGROUP_1"],
            2: stages["SUBGROUP_2"],
            3: stages["SUBGROUP_3"],
        }
        group_matches = list(
            Match.objects.filter(stage__is_group=True)
            .select_related("home_team"))
        rounds = round_by_match(group_matches)
        moved = 0
        for match in group_matches:
            target = subgroup[rounds[match.id]]
            if match.stage_id != target.id:
                match.stage = target
                match.save(update_fields=["stage"])
                moved += 1
        return moved

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

    @staticmethod
    def _assign_names(of_matches: list[dict]) -> None:
        """Fija ``name`` legible en cada item (in-place).

        Se numera por posición cronológica dentro de la ronda ("Cuartos
        3"). El identificador numérico del partido es ``of_number``; el
        cruce se traza por él (los placeholders de OF lo referencian, p.
        ej. "W101"). Los grupos quedan con ``name`` vacío.
        """
        round_count: dict[str, int] = defaultdict(int)
        for item in sorted(of_matches, key=lambda m: m["of_number"]):
            rnd = item["round"]
            if rnd.startswith("Matchday"):
                item["name"] = ""
                continue
            if rnd == "Match for third place":
                item["name"] = "Tercer lugar"
            elif rnd == "Final":
                item["name"] = "Final"
            else:
                round_count[rnd] += 1
                item["name"] = f"{ROUND_NAME_ES[rnd]} {round_count[rnd]}"
