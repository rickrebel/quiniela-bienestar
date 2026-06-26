"""Posiciones por grupo en tres variantes: est (solo las predicciones
del usuario), real (solo partidos FINISHED) y mix (resultado real
donde existe, predicción del usuario para el resto).

PJ y tarjetas son SIEMPRE datos reales en las tres variantes: no
existen tarjetas estimadas y un PJ "estimado" inflaría los jugados
con partidos aún no disputados. Las tablas reflejan las predicciones
guardadas al cargar la página: el autosave no las recalcula.
"""

from dataclasses import dataclass

from pool.models import Prediction
from tournament.models import Match, Team

VARIANTS = ("est", "mix", "real")


@dataclass
class StandingRow:
    team: Team
    played: int = 0   # solo FINISHED; idéntico en las 3 variantes
    yellow: int = 0   # tarjetas reales (None cuenta como 0)
    red: int = 0
    points: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def sort_key(self) -> tuple:
        # Desempate GLOBAL (Pts, DG, GF, fair play). En 2026 el primer
        # criterio tras los puntos es el enfrentamiento directo, que se
        # aplica antes en ``_break_tie``; esto es solo el fallback cuando
        # el directo no separa.
        return (-self.points, -self.goal_diff, -self.goals_for,
                self.red, self.yellow)


@dataclass
class VariantTable:
    variant: str             # "est" | "mix" | "real"
    rows: list[StandingRow]  # ya ordenadas


@dataclass
class GroupStandings:
    group: str
    tables: list[VariantTable]
    # Orden mix para el render inicial; cada Team lleva anotados
    # order_est/order_mix/order_real (0-based) para style.order.
    teams: list[Team]


def _apply(home: StandingRow, away: StandingRow, hg: int, ag: int) -> None:
    home.goals_for += hg
    home.goals_against += ag
    away.goals_for += ag
    away.goals_against += hg
    if hg > ag:
        home.points += 3
        home.won += 1
        away.lost += 1
    elif hg < ag:
        away.points += 3
        away.won += 1
        home.lost += 1
    else:
        home.points += 1
        away.points += 1
        home.drawn += 1
        away.drawn += 1


Pair = tuple[int, int, int, int]  # (home_id, away_id, home_goals, away_goals)


def _mini_table(
    rows: list[StandingRow], pairs: list[Pair]
) -> dict[int, tuple[int, int, int]]:
    """Mini-liga del enfrentamiento directo: (pts, DG, GF) de cada equipo
    contando SOLO los partidos jugados entre los equipos de ``rows``."""
    ids = {r.team.id for r in rows}
    agg: dict[int, list[int]] = {tid: [0, 0, 0] for tid in ids}  # pts gf ga
    for home_id, away_id, hg, ag in pairs:
        if home_id not in ids or away_id not in ids:
            continue
        agg[home_id][1] += hg
        agg[home_id][2] += ag
        agg[away_id][1] += ag
        agg[away_id][2] += hg
        if hg > ag:
            agg[home_id][0] += 3
        elif hg < ag:
            agg[away_id][0] += 3
        else:
            agg[home_id][0] += 1
            agg[away_id][0] += 1
    return {tid: (pts, gf - ga, gf) for tid, (pts, gf, ga) in agg.items()}


def _break_tie(rows: list[StandingRow], pairs: list[Pair]) -> list[StandingRow]:
    """Ordena equipos empatados a puntos por la mini-liga del directo
    (pts, DG, GF entre ellos), reaplicada a cada subgrupo aún empatado. Si
    el directo no separa a nadie, cae al desempate global (``sort_key``)."""
    if len(rows) == 1:
        return list(rows)
    mini = _mini_table(rows, pairs)
    ordered = sorted(rows, key=lambda r: tuple(-v for v in mini[r.team.id]))
    blocks: list[list[StandingRow]] = []
    for row in ordered:
        if blocks and mini[blocks[-1][0].team.id] == mini[row.team.id]:
            blocks[-1].append(row)
        else:
            blocks.append([row])
    if len(blocks) == 1:
        return sorted(rows, key=lambda r: r.sort_key)
    result: list[StandingRow] = []
    for block in blocks:
        result.extend(_break_tie(block, pairs))
    return result


def rank_group(rows: list[StandingRow], pairs: list[Pair]) -> list[StandingRow]:
    """Ordena un grupo: primero por puntos; cada empate a puntos se resuelve
    por enfrentamiento directo (regla FIFA 2026)."""
    by_points = sorted(rows, key=lambda r: -r.points)
    result: list[StandingRow] = []
    block: list[StandingRow] = []
    for row in by_points:
        if block and block[-1].points != row.points:
            result.extend(_break_tie(block, pairs))
            block = []
        block.append(row)
    if block:
        result.extend(_break_tie(block, pairs))
    return result


def build_group_standings(
    matches: list[Match], predictions: dict[int, Prediction]
) -> dict[str, GroupStandings]:
    """Tablas por grupo a partir de los matches ya cargados (con
    ``select_related`` de equipos) y las predicciones del usuario
    indexadas por ``match_id``. No consulta la BD."""
    # select_related crea instancias distintas de Team por fila; el
    # registro canónico garantiza que las anotaciones order_* caigan
    # en las mismas instancias que se devuelven en ``teams``.
    canonical: dict[str, dict[int, Team]] = {}
    rows: dict[str, dict[str, dict[int, StandingRow]]] = {}
    # Partidos jugados por grupo y variante, para la mini-liga del directo.
    pairs: dict[str, dict[str, list[Pair]]] = {}

    for match in matches:
        if match.home_team is None or match.away_team is None:
            continue
        group = match.home_team.group_name
        teams = canonical.setdefault(group, {})
        home = teams.setdefault(match.home_team.id, match.home_team)
        away = teams.setdefault(match.away_team.id, match.away_team)
        by_variant = rows.setdefault(group, {v: {} for v in VARIANTS})
        by_pairs = pairs.setdefault(group, {v: [] for v in VARIANTS})

        finished = (
            match.status == "FINISHED"
            and match.home_goals is not None
            and match.away_goals is not None
        )
        real = (match.home_goals, match.away_goals) if finished else None
        pred = predictions.get(match.id)
        est = (pred.home_goals, pred.away_goals) if pred else None
        sources = {"est": est, "real": real, "mix": real or est}

        for variant in VARIANTS:
            vrows = by_variant[variant]
            hrow = vrows.setdefault(home.id, StandingRow(team=home))
            arow = vrows.setdefault(away.id, StandingRow(team=away))
            source = sources[variant]
            if source is not None:
                _apply(hrow, arow, *source)
                by_pairs[variant].append((home.id, away.id, *source))
            if finished:
                hrow.played += 1
                arow.played += 1
                hrow.yellow += match.home_yellow or 0
                hrow.red += match.home_red or 0
                arow.yellow += match.away_yellow or 0
                arow.red += match.away_red or 0

    standings: dict[str, GroupStandings] = {}
    for group, by_variant in rows.items():
        tables = []
        for variant in VARIANTS:
            ordered = rank_group(
                list(by_variant[variant].values()),
                pairs[group][variant],
            )
            for i, row in enumerate(ordered):
                setattr(row.team, f"order_{variant}", i)
            tables.append(VariantTable(variant=variant, rows=ordered))
        mix_rows = next(t.rows for t in tables if t.variant == "mix")
        standings[group] = GroupStandings(
            group=group,
            tables=tables,
            teams=[r.team for r in mix_rows],
        )
    return standings
