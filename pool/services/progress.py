"""Datos para la gráfica "Historia": la evolución del acumulado de cada
participante, tanda por tanda.

Lee ``ScoreSnapshot`` (ya congelado por la evaluación) y arma una
estructura lista para serializar a JSON e incrustar en la página. El
ranking y la preselección por defecto salen de ``build_leaderboard``.
Cada partido FINISHED tiene un snapshot por usuario aunque no lo haya
predicho, así que no hay huecos: cada tick trae valor para todos.
"""

from datetime import timedelta

from pool.models import Quiniela, ScoreSnapshot, User
from pool.services.leaderboard import build_leaderboard
from tournament.models import Match


def _match_label(match: Match) -> str:
    """Etiqueta corta del partido (códigos FIFA, o placeholder en
    eliminatorias sin equipos resueltos)."""
    home = match.home_team.fifa_code if match.home_team_id else (
        match.home_placeholder or "?")
    away = match.away_team.fifa_code if match.away_team_id else (
        match.away_placeholder or "?")
    return f"{home}–{away}"


def build_progress(quiniela: Quiniela, me: User) -> dict:
    """Estructura serializable para la gráfica de ``quiniela``.

    - ``ticks``: tandas en orden; el tick 0 es la salida (todos en cero)
      para que las líneas nazcan de un origen común. Cada tick trae su
      fecha local, la fase y los partidos que lo componen (para los
      modos de eje X: tanda, día y partido).
    - ``series``: una por jugador con sus puntos acumulados por tick.
    - ``defaults``: ids preseleccionados (top 1, top 2 y peor real); el
      usuario activo se dibuja siempre aparte, no entra aquí.
    """
    finished = list(
        Match.objects.filter(
            status="FINISHED",
            home_goals__isnull=False,
            away_goals__isnull=False,
        )
        .select_related("home_team", "away_team", "stage", "stadium")
        .order_by("datetime", "of_number")
    )

    # Tandas: partidos con el mismo ``datetime`` comparten tick (el
    # acumulado es por tanda, no por partido).
    tick_of_dt: dict = {}
    ticks: list[dict] = [{"date": "", "stage": "Salida", "matches": []}]
    for m in finished:
        if m.datetime not in tick_of_dt:
            tick_of_dt[m.datetime] = len(ticks)
            offset = m.stadium.utc_offset if m.stadium_id else 0
            local = (m.datetime + timedelta(hours=offset or 0)).date()
            ticks.append({
                "date": local.isoformat(),
                "stage": m.stage.short_name,
                "matches": [],
            })
        ticks[tick_of_dt[m.datetime]]["matches"].append(_match_label(m))

    board = build_leaderboard(quiniela)
    players = [r for r in board.rows if r.has_played]
    index_of_user = {r.user.id: i for i, r in enumerate(players)}

    # Puntos por (jugador, tick). Los snapshots de partidos simultáneos
    # repiten valor; asignar por tick basta.
    points = [[0.0] * len(ticks) for _ in players]
    snaps = ScoreSnapshot.objects.filter(quiniela=quiniela).values_list(
        "user_id", "match__datetime", "cumulative_points")
    for uid, dt, cumulative in snaps:
        i = index_of_user.get(uid)
        t = tick_of_dt.get(dt)
        if i is not None and t is not None:
            points[i][t] = float(cumulative)

    series = [
        {
            "id": r.user.id,
            "name": r.user.first_name or r.user.email,
            "virtual": r.user.is_virtual,
            "me": r.user.id == me.id,
            "position": r.position,
            "points": row,
        }
        for r, row in zip(players, points)
    ]

    # Preselección: top 1, top 2 y el peor real (la virtual queda fuera
    # de los defaults pero seleccionable; el activo se pinta aparte).
    reals = [r for r in players if not r.user.is_virtual]
    defaults: list[int] = []
    for row in (reals[:1] + reals[1:2] + reals[-1:]):
        if row.user.id != me.id and row.user.id not in defaults:
            defaults.append(row.user.id)

    return {"ticks": ticks, "series": series, "defaults": defaults}
