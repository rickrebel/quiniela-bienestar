"""Tabla de posiciones: agrega los puntos de cada usuario.

Todo en memoria (dos queries): a esta escala (decenas de usuarios por
72 partidos) no amerita agregación en SQL ni cache. Solo cuentan los
partidos FINISHED con marcador.
"""

from dataclasses import dataclass

from pool.models import Prediction, User
from pool.services.scoring import score_detail
from tournament.models import Match


@dataclass
class LeaderboardRow:
    position: int
    user: User
    points: int
    exact: int       # marcadores exactos
    diffs: int       # bonos por diferencia (disjunto de exact)
    has_played: bool  # tiene al menos una predicción evaluada

    @property
    def sort_key(self) -> tuple:
        return (-self.points, -self.exact, -self.diffs)


@dataclass
class Leaderboard:
    rows: list[LeaderboardRow]
    # Alcanzables hasta ahora: 5 por partido con ganador, 4 por empate
    # (en empate el bono de diferencia no aplica).
    max_points: int

    def row_for(self, user: User) -> LeaderboardRow | None:
        return next((r for r in self.rows if r.user.id == user.id), None)


def build_leaderboard() -> Leaderboard:
    """Posiciones de todos los usuarios activos, con empates compartidos
    (1-2-2-4) sobre la tupla (puntos, exactos, diferencias)."""
    results = {
        match_id: (home, away)
        for match_id, home, away in Match.objects.filter(
            status="FINISHED",
            home_goals__isnull=False,
            away_goals__isnull=False,
        ).values_list("id", "home_goals", "away_goals")
    }
    max_points = sum(
        4 if home == away else 5 for home, away in results.values()
    )

    rows = {
        user.id: LeaderboardRow(
            position=0, user=user, points=0, exact=0, diffs=0,
            has_played=False,
        )
        for user in User.objects.filter(is_active=True)
    }

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
        row.exact += detail.exact
        row.diffs += detail.diff_bonus
        row.has_played = True

    ordered = sorted(
        rows.values(),
        key=lambda r: (*r.sort_key, (r.user.first_name or "").lower()),
    )
    for i, row in enumerate(ordered):
        if i and row.sort_key == ordered[i - 1].sort_key:
            row.position = ordered[i - 1].position
        else:
            row.position = i + 1
    return Leaderboard(rows=ordered, max_points=max_points)
