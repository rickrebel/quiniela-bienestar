"""Deriva la ronda (1.ª/2.ª/3.ª jornada) de cada partido de grupo.

OF numera las jornadas de forma GLOBAL (``Matchday 1``..``Matchday 17``),
no por grupo, así que la ronda real no sale del campo ``round``. Se deriva
del calendario: dentro de un grupo, sus 6 partidos ordenados por fecha
forman 3 rondas de 2 (R1 = los dos más tempranos, etc.). Verificado contra
el fixture del Mundial 2026 (12 grupos × 6 partidos, corte limpio 2+2+2).
"""

from collections import defaultdict

# (key, name, short_name, order) de las 3 sub-fases de grupos. ``order`` es
# el definitivo (las eliminatorias quedan en 4..8). Se reutiliza tanto en el
# bootstrap como en el seed desde cero.
SUBGROUP_STAGES = [
    ("SUBGROUP_1", "Grupos · jornada 1", "Jornada 1", 1),
    ("SUBGROUP_2", "Grupos · jornada 2", "Jornada 2", 2),
    ("SUBGROUP_3", "Grupos · jornada 3", "Jornada 3", 3),
]
SUBGROUP_COLOR = "#4CAF50"


def round_by_match(matches) -> dict[int, int]:
    """Mapa ``match_id`` -> ronda (1..3) por grupo.

    ``matches`` debe traer ``home_team`` cargado (para ``group_name``). Los
    partidos de cada grupo se ordenan por ``datetime`` y se parten en pares:
    índices 0-1 -> ronda 1, 2-3 -> ronda 2, 4-5 -> ronda 3.
    """
    by_group: dict[str, list] = defaultdict(list)
    for match in matches:
        if match.home_team is None:
            continue
        by_group[match.home_team.group_name].append(match)

    result: dict[int, int] = {}
    for group_matches in by_group.values():
        group_matches.sort(key=lambda m: m.datetime)
        for index, match in enumerate(group_matches):
            result[match.id] = index // 2 + 1
    return result
