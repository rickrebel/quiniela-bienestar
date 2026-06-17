"""Tabla de posiciones: agrega los puntos de cada usuario.

Todo en memoria (dos queries): a esta escala (decenas de usuarios por
72 partidos) no amerita agregación en SQL ni cache. Solo cuentan los
partidos FINISHED con marcador.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q

from pool.models import Prediction, User
from pool.services.scoring import score_detail
from tournament.models import Match


@dataclass
class LeaderboardRow:
    position: int
    user: User
    points: int
    outcomes: int    # resultados atinados (incluye exactos y diferencias)
    exact: int       # marcadores exactos
    diffs: int       # bonos por diferencia (incluye los exactos no-empate)
    has_played: bool  # tiene al menos una predicción evaluada
    # Movimiento de posición desde el último partido (trend_batch) o la
    # última jornada (trend_day): "up", "down" o None (sin cambio, sin
    # partido previo con que comparar, o perfil virtual).
    trend_batch: str | None = None
    trend_day: str | None = None

    @property
    def sort_key(self) -> tuple:
        return (-self.points, -self.exact, -self.diffs)


def _dense_positions(points_by_user: dict[int, int]) -> dict[int, int]:
    """Ranking denso (1-2-2-3) por puntos: los empates comparten lugar y no
    recorren al siguiente. Mismo criterio que el loop de posiciones de
    ``build_leaderboard``, parametrizado para reusarse con los puntos
    "previos" de cada baseline. Devuelve user_id -> posición."""
    positions: dict[int, int] = {}
    previous_points = None
    previous_position = 0
    for user_id, points in sorted(points_by_user.items(), key=lambda kv: -kv[1]):
        if previous_points is None or points != previous_points:
            previous_position += 1
        positions[user_id] = previous_position
        previous_points = points
    return positions


def _trend(previous_position: int, current_position: int) -> str | None:
    """Flecha según el cambio de posición (menor número = mejor lugar)."""
    if previous_position > current_position:
        return "up"
    if previous_position < current_position:
        return "down"
    return None


@dataclass
class Leaderboard:
    rows: list[LeaderboardRow]
    # Alcanzables hasta ahora: 5 por partido con ganador, 4 por empate
    # (en empate el bono de diferencia no aplica).
    max_points: int

    def row_for(self, user: User) -> LeaderboardRow | None:
        return next((r for r in self.rows if r.user.id == user.id), None)


def build_leaderboard() -> Leaderboard:
    """Posiciones de todos los usuarios activos. La posición depende solo
    de los puntos, con ranking denso (1-2-2-3: los empates comparten lugar
    y no recorren al siguiente). Exactos y diferencias solo ordenan
    visualmente dentro de un empate, no cambian la posición.

    El perfil virtual entra a la tabla (ordenado por sus puntos) pero
    queda fuera del ranking: conserva ``position=0`` y no desplaza a
    nadie."""
    finished = list(
        Match.objects.filter(
            status="FINISHED",
            home_goals__isnull=False,
            away_goals__isnull=False,
        ).values_list(
            "id", "home_goals", "away_goals", "datetime", "stadium__utc_offset"
        )
    )
    results = {mid: (home, away) for mid, home, away, _, _ in finished}
    max_points = sum(
        4 if home == away else 5 for home, away in results.values()
    )

    # Baselines para la flecha de tendencia. "batch" = última tanda (los
    # partidos que arrancaron a la misma hora UTC); "day" = última jornada
    # (todos los del día más reciente del torneo, en fecha local del estadio,
    # ya que matchday no se persiste). La posición previa se recalcula
    # excluyendo esos partidos: si al excluirlos no queda nada (un solo
    # bloque en todo el torneo), no hay con qué comparar y no se muestra.
    batch_ids: set[int] = set()
    day_ids: set[int] = set()
    if finished:
        local_date = {
            mid: (dt + timedelta(hours=offset or 0)).date()
            for mid, _, _, dt, offset in finished
        }
        last_datetime = max(dt for _, _, _, dt, _ in finished)
        last_day = max(local_date.values())
        batch_ids = {mid for mid, _, _, dt, _ in finished if dt == last_datetime}
        day_ids = {mid for mid in results if local_date[mid] == last_day}

    rows = {
        user.id: LeaderboardRow(
            position=0, user=user, points=0, outcomes=0, exact=0, diffs=0,
            has_played=False,
        )
        for user in User.objects.filter(Q(is_active=True) | Q(is_virtual=True))
    }

    # Puntos "previos" por baseline: el total menos lo ganado en los partidos
    # excluidos. Sobre ellos se recalcula la posición previa.
    prev_batch_points: dict[int, int] = defaultdict(int)
    prev_day_points: dict[int, int] = defaultdict(int)

    predictions = Prediction.objects.filter(
        match_id__in=results, user_id__in=rows
    ).values_list("user_id", "match_id", "home_goals", "away_goals")
    for user_id, match_id, pred_home, pred_away in predictions:
        actual_home, actual_away = results[match_id]
        detail = score_detail(pred_home, pred_away, actual_home, actual_away)
        if detail is None:
            continue
        row = rows[user_id]
        row.points += detail.points
        row.outcomes += detail.outcome
        row.exact += detail.exact
        # El exacto (salvo empate) también acertó la diferencia: cuenta
        # como bono de diferencia aunque ``diff_bonus`` salga disjunto.
        row.diffs += detail.diff_bonus or (detail.exact and actual_home != actual_away)
        row.has_played = True
        if match_id not in batch_ids:
            prev_batch_points[user_id] += detail.points
        if match_id not in day_ids:
            prev_day_points[user_id] += detail.points

    ordered = sorted(
        rows.values(),
        key=lambda r: (*r.sort_key, (r.user.first_name or "").lower()),
    )
    previous = None
    for row in ordered:
        if row.user.is_virtual:
            continue
        if previous is None:
            row.position = 1
        elif row.points == previous.points:
            row.position = previous.position
        else:
            row.position = previous.position + 1
        previous = row

    _assign_trends(ordered, batch_ids, results, prev_batch_points, "batch")
    _assign_trends(ordered, day_ids, results, prev_day_points, "day")
    return Leaderboard(rows=ordered, max_points=max_points)


def _assign_trends(
    ordered: list[LeaderboardRow],
    excluded_ids: set[int],
    results: dict,
    prev_points: dict[int, int],
    attr: str,
) -> None:
    """Setea ``trend_batch``/``trend_day`` comparando la posición actual con
    la previa (recalculada sobre ``prev_points``). No hace nada si no quedan
    partidos previos al excluir (no hay con qué comparar)."""
    if not excluded_ids or len(excluded_ids) == len(results):
        return
    ranked = {
        row.user.id: prev_points[row.user.id]
        for row in ordered
        if not row.user.is_virtual
    }
    prev_positions = _dense_positions(ranked)
    for row in ordered:
        if row.user.is_virtual:
            continue
        setattr(row, f"trend_{attr}", _trend(prev_positions[row.user.id], row.position))
