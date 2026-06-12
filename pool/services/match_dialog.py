"""Payload del dialog de detalle de partido + predicciones de todos.

Construye los datos que cada página embebe con ``json_script`` y que
``static/match_dialog.js`` renderiza al hacer clic en un partido. La
privacidad se resuelve aquí (servidor): las fases sin
``Stage.is_past_deadline`` viajan sin predicciones, no ocultas por CSS.
"""

from collections import defaultdict
from datetime import timedelta
from itertools import groupby
from typing import Sequence

from django.templatetags.static import static

from pool.models import Prediction, User
from pool.services.scoring import ScoreDetail, score_detail
from pool.utils import format_day, format_time
from tournament.models import Match, Stage


def group_predictions(rows: list[dict]) -> list[dict]:
    """Agrupa predicciones por diferencia de goles a favor del local.

    Grupos en orden descendente de diferencia (+3…0…−2); dentro de cada
    grupo, suma de goles descendente (3-2 antes que 1-0). Ambos sorts
    son estables, así que a igual suma se conserva el orden de entrada
    (las vistas ya ordenan por nombre).
    """
    ordered = sorted(rows, key=lambda r: r["home"] + r["away"], reverse=True)
    ordered = sorted(ordered, key=lambda r: r["home"] - r["away"],
                     reverse=True)
    return [
        {"diff": diff, "predictions": list(preds)}
        for diff, preds in groupby(
            ordered, key=lambda r: r["home"] - r["away"]
        )
    ]


def diff_label(diff: int, home: str, away: str) -> str:
    """Encabezado de grupo: '{equipo} por {n}' o 'Empate'."""
    if diff == 0:
        return "Empate"
    team = home if diff > 0 else away
    return f"{team} por {abs(diff)}"


def points_display(detail: ScoreDetail | None) -> dict | None:
    """Desglose visual de puntos, mismo contrato que ``annotate_result``.

    ``base`` excluye el bono de diferencia porque en pantalla el "+1" va
    como badge aparte (mostrar el total junto al badge se leería como
    total+1). ``kind`` alimenta el color: miss/hit/exact.
    """
    if detail is None:
        return None
    if detail.points == 0:
        kind = "miss"
    elif detail.exact:
        kind = "exact"
    else:
        kind = "hit"
    return {
        "total": detail.points,
        "base": detail.points - (1 if detail.diff_bonus else 0),
        "bonus": detail.diff_bonus,
        "kind": kind,
    }


def scorers_by_team(match: Match) -> tuple[list[str], list[str]]:
    """Goleadores ("35' Fulano") por equipo desde ``raw_fd["goals"]``.

    El formato es el del endpoint detail de FD; si el snapshot no trae
    goles (p. ej. solo se sincronizó el list endpoint) degrada a listas
    vacías sin romper la página.
    """
    raw = match.raw_fd or {}
    home_id = (raw.get("homeTeam") or {}).get("id")
    home, away = [], []
    for goal in raw.get("goals") or []:
        scorer = (goal.get("scorer") or {}).get("name", "")
        line = f"{goal.get('minute', '?')}' {scorer}".strip()
        if (goal.get("team") or {}).get("id") == home_id:
            home.append(line)
        else:
            away.append(line)
    return home, away


def phase_label(match: Match) -> str:
    """Etiqueta de fase: 'Grupo X' en grupos, nombre del partido o de
    la fase en eliminatorias."""
    if match.stage.key == Stage.GROUP_STAGE:
        return f"Grupo {match.home_team.group_name}"
    return match.name or match.stage.name


def _team_payload(team, placeholder: str) -> dict:
    if team is None:
        return {"name": placeholder, "placeholder": True}
    return {
        "name": team.name_es,
        "flag": static(team.flag_path) if team.flag_path else None,
    }


def _match_payload(match: Match, finished: bool) -> dict:
    local_dt = match.datetime + timedelta(hours=match.stadium.utc_offset)
    payload = {
        "id": match.id,
        "phase": phase_label(match),
        "home": _team_payload(match.home_team, match.home_placeholder),
        "away": _team_payload(match.away_team, match.away_placeholder),
        # day/time son hora de la sede (fallback); el cliente muestra la
        # zona del espectador a partir de utc (local_time.js).
        "utc": match.datetime.isoformat(),
        "day": format_day(local_dt),
        "time": format_time(local_dt),
        "stadium": match.stadium.name_es or match.stadium.city,
        "stadium_flag": (
            static(match.stadium.flag_path)
            if match.stadium.flag_path else None
        ),
        "finished": finished,
        "score": None,
        "penalties": None,
        "cards": None,
        "scorers": None,
        "revealed": match.stage.is_past_deadline,
    }
    if not finished:
        return payload
    payload["score"] = {"home": match.home_goals, "away": match.away_goals}
    if match.decided_by == Match.PENALTY_SHOOTOUT:
        payload["penalties"] = {
            "home": match.home_penalties, "away": match.away_penalties
        }
    payload["cards"] = {
        "home": {"yellow": match.home_yellow or 0,
                 "red": match.home_red or 0},
        "away": {"yellow": match.away_yellow or 0,
                 "red": match.away_red or 0},
    }
    home_scorers, away_scorers = scorers_by_team(match)
    payload["scorers"] = {"home": home_scorers, "away": away_scorers}
    return payload


def build_match_dialog_payload(
    matches: Sequence[Match], user: User
) -> list[dict]:
    """Datos del dialog para una lista de partidos (ambas vistas).

    Una sola query de predicciones, limitada a fases ya cerradas: antes
    del deadline las predicciones ajenas son privadas y el JSON no debe
    llevarlas. Requiere ``select_related("stage", "stadium", "home_team",
    "away_team")`` en ``matches`` para no degenerar en N+1.
    """
    closed = {m.stage_id for m in matches if m.stage.is_past_deadline}
    rows_by_match: dict[int, list[dict]] = defaultdict(list)
    if closed:
        predictions = (
            Prediction.objects
            .filter(match__in=matches, match__stage_id__in=closed)
            .select_related("user")
            .order_by("user__first_name")
        )
        finished_ids = {
            m.id for m in matches
            if m.status == "FINISHED"
            and m.home_goals is not None and m.away_goals is not None
        }
        matches_by_id = {m.id: m for m in matches}
        for pred in predictions:
            match = matches_by_id[pred.match_id]
            detail = (
                score_detail(pred.home_goals, pred.away_goals,
                             match.home_goals, match.away_goals)
                if pred.match_id in finished_ids else None
            )
            rows_by_match[pred.match_id].append({
                "name": pred.user.first_name or pred.user.email,
                "home": pred.home_goals,
                "away": pred.away_goals,
                "is_self": pred.user_id == user.id,
                "points": points_display(detail),
            })

    result = []
    for match in matches:
        finished = (
            match.status == "FINISHED"
            and match.home_goals is not None
            and match.away_goals is not None
        )
        payload = _match_payload(match, finished)
        if payload["revealed"]:
            groups = group_predictions(rows_by_match.get(match.id, []))
            for group in groups:
                group["label"] = diff_label(
                    group["diff"],
                    payload["home"]["name"], payload["away"]["name"],
                )
            payload["groups"] = groups
        result.append(payload)
    return result
