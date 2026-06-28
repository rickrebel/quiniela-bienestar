"""Datos para la gráfica "Historia": la evolución del acumulado de cada
participante, tanda por tanda.

Lee ``ScoreSnapshot`` (ya congelado por la evaluación) y arma una
estructura lista para serializar a JSON e incrustar en la página. El
ranking y la preselección por defecto salen de ``build_leaderboard``.
Cada partido FINISHED tiene un snapshot por usuario aunque no lo haya
predicho, así que no hay huecos: cada tick trae valor para todos.
"""

from datetime import timedelta

from django.templatetags.static import static

from pool.models import (
    Prediction, Quiniela, ScoreSnapshot, User, UserQuiniela)
from pool.services.evaluation import multiplier_by_stage
from pool.services.leaderboard import build_leaderboard
from tournament.models import Match

# Tope de líneas comparadas: igual al tamaño de la paleta del front
# (--chart-1..8, MAX_COMPARE en progress.js).
MAX_COMPARE = 8


def _match_entry(match: Match) -> dict:
    """Datos del partido para el eje X: códigos FIFA (o placeholder en
    eliminatorias sin equipos resueltos) y la URL estática de cada bandera
    (vacía si no hay), que el modo "partido" apila local sobre visitante."""
    def code(team, placeholder):
        return team.fifa_code if team else (placeholder or "?")

    def flag(team):
        return static(team.flag_path) if team and team.flag_path else ""

    return {
        "home": code(match.home_team if match.home_team_id else None,
                     match.home_placeholder),
        "away": code(match.away_team if match.away_team_id else None,
                     match.away_placeholder),
        "home_flag": flag(match.home_team if match.home_team_id else None),
        "away_flag": flag(match.away_team if match.away_team_id else None),
    }


def _start_cutoff(quiniela: Quiniela):
    """``datetime`` del primer partido terminado de la primera ventana (por
    ``order``) en la que la quiniela ya tiene predicciones.

    Recorta el tramo plano inicial de las ventanas que nacieron cerradas:
    bienestar, por ejemplo, arrancó en la Jornada 2 (nadie predijo la 1),
    así que la gráfica debe empezar ahí y no en el saque del torneo. La
    ``resolved_opens_at`` no sirve como señal porque cae al ``Stage``
    compartido y todas las jornadas resuelven una fecha. ``None`` si la
    quiniela aún no tiene ninguna predicción (no se recorta nada).
    """
    predicted_stage_ids = set(
        Prediction.objects.filter(quiniela=quiniela)
        .values_list("match__stage_id", flat=True)
    )
    if not predicted_stage_ids:
        return None
    windows = quiniela.windows.order_by("order").prefetch_related("stages")
    for window in windows:
        stage_ids = [s.id for s in window.stages.all()]
        if not predicted_stage_ids.intersection(stage_ids):
            continue
        return (
            Match.objects.filter(
                stage_id__in=stage_ids,
                status="FINISHED",
                home_goals__isnull=False,
                away_goals__isnull=False,
            )
            .order_by("datetime")
            .values_list("datetime", flat=True)
            .first()
        )
    return None


def build_progress(quiniela: Quiniela, me: User) -> dict:
    """Estructura serializable para la gráfica de ``quiniela``.

    - ``ticks``: tandas en orden; el tick 0 es la salida (todos en cero)
      para que las líneas nazcan de un origen común. Cada tick trae su
      fecha local, el ``stage`` (nombre corto), la ``phase`` gruesa (las 3
      jornadas de grupos colapsan en "Grupos"; sirve para el divisor de
      fases) y los partidos que lo componen (eje X por partido).
    - ``series``: una por jugador con sus puntos acumulados por tick.
    - ``defaults``: ids preseleccionados. Si ``me`` ya guardó su
      comparación en ``UserQuiniela.history_compare`` se usa esa (saneada
      y en su orden); si no (``None``), se calculan (top 1, top 2 y peor
      real). El usuario activo se dibuja siempre aparte, no entra aquí.
    """
    cutoff = _start_cutoff(quiniela)
    match_qs = Match.objects.filter(
        status="FINISHED",
        home_goals__isnull=False,
        away_goals__isnull=False,
    )
    if cutoff is not None:
        match_qs = match_qs.filter(datetime__gte=cutoff)
    finished = list(
        match_qs
        .select_related("home_team", "away_team", "stage", "stadium")
        .order_by("datetime", "of_number")
    )

    # Tandas: partidos con el mismo ``datetime`` comparten tick (el
    # acumulado es por tanda, no por partido). El ``multiplier`` de la
    # ventana pondera el ancho del bloque en el eje X (resuelto por fase).
    mult_by_stage = multiplier_by_stage(quiniela)
    tick_of_dt: dict = {}
    ticks: list[dict] = [
        {"date": "", "stage": "Salida", "phase": "Salida",
         "matches": [], "multiplier": 1}
    ]
    for m in finished:
        if m.datetime not in tick_of_dt:
            tick_of_dt[m.datetime] = len(ticks)
            offset = m.stadium.utc_offset if m.stadium_id else 0
            local = (m.datetime + timedelta(hours=offset or 0)).date()
            # ``phase`` agrupa las 3 jornadas de grupos bajo una sola fase
            # para el divisor vertical del eje X (las eliminatorias ya son
            # una fase cada una).
            phase = "Grupos" if m.stage.is_group else m.stage.short_name
            ticks.append({
                "date": local.isoformat(),
                "stage": m.stage.short_name,
                "phase": phase,
                "matches": [],
                "multiplier": float(mult_by_stage.get(m.stage_id, 1)),
            })
        ticks[tick_of_dt[m.datetime]]["matches"].append(_match_entry(m))

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

    # Preselección guardada (``UserQuiniela.history_compare``) o, si nunca
    # se personalizó (``None``), el cálculo por defecto. ``[]`` guardado
    # es una elección deliberada (no comparar a nadie) y se respeta.
    saved = _saved_selection(me, quiniela)
    if saved is not None:
        selectable = {s["id"] for s in series if not s["me"]}
        defaults = [uid for uid in dict.fromkeys(saved)
                    if uid in selectable][:MAX_COMPARE]
    else:
        # Top 1, top 2 y el peor real (la virtual queda fuera de los
        # defaults pero seleccionable; el activo se pinta aparte).
        reals = [r for r in players if not r.user.is_virtual]
        defaults = []
        for row in (reals[:1] + reals[1:2] + reals[-1:]):
            if row.user.id != me.id and row.user.id not in defaults:
                defaults.append(row.user.id)

    return {"ticks": ticks, "series": series, "defaults": defaults}


def _saved_selection(me: User, quiniela: Quiniela) -> list[int] | None:
    """Selección comparada que ``me`` guardó para esta quiniela.

    ``None`` si no hay membresía o nunca se personalizó (cae a defaults);
    una lista (posiblemente vacía) si el usuario la fijó.
    """
    membership = (
        UserQuiniela.objects.filter(user=me, quiniela=quiniela)
        .values_list("history_compare", flat=True)
        .first()
    )
    return membership
