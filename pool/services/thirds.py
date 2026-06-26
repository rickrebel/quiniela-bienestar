"""Ranking de los mejores terceros del Mundial 2026.

Con 12 grupos hay 12 terceros y clasifican los 8 mejores. El desempate es
puntos, diferencia de goles, goles a favor y fair play; NO hay enfrentamiento
directo (los terceros vienen de grupos distintos). Se calcula en las tres
variantes (est/mix/real), igual que la tabla de posiciones.
"""

from dataclasses import dataclass

from pool.services.standings import VARIANTS, GroupStandings
from tournament.models import Team

QUALIFYING_THIRDS = 8


@dataclass
class ThirdRow:
    team: Team
    group: str
    points: int
    goal_diff: int
    goals_for: int
    yellow: int
    red: int
    qualified: bool = False
    # No. del partido del cruce inicial (anexo C); lo fija la vista, no
    # build_thirds, porque depende de los partidos de LAST_32.
    match_number: int | None = None

    @property
    def sort_key(self) -> tuple:
        return (-self.points, -self.goal_diff, -self.goals_for,
                self.red, self.yellow)


def build_thirds(
    standings: dict[str, GroupStandings],
) -> dict[str, list[ThirdRow]]:
    """Ranking de terceros por variante. Toma la 3.ª fila de cada grupo,
    ordena por (pts, DG, GF, fair play) y marca clasificados a los 8
    primeros. El empate residual queda en orden estable (sin ranking FIFA)."""
    result: dict[str, list[ThirdRow]] = {}
    for variant in VARIANTS:
        thirds: list[ThirdRow] = []
        for group, gs in standings.items():
            table = next(t for t in gs.tables if t.variant == variant)
            if len(table.rows) < 3:
                continue
            row = table.rows[2]
            thirds.append(
                ThirdRow(
                    team=row.team, group=group, points=row.points,
                    goal_diff=row.goal_diff, goals_for=row.goals_for,
                    yellow=row.yellow, red=row.red,
                )
            )
        thirds.sort(key=lambda t: t.sort_key)
        for i, third in enumerate(thirds):
            third.qualified = i < QUALIFYING_THIRDS
        result[variant] = thirds
    return result
