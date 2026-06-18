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
from pool.services.scoring import ScoreDetail, result_chips, score_detail
from pool.utils import format_day, format_time
from tournament.models import Match


def group_predictions(rows: list[dict]) -> list[dict]:
    """Agrupa por diferencia de goles y, dentro, por marcador exacto.

    Grupos en orden descendente de diferencia (+3…0…−2). Cada grupo trae
    un subgrupo por marcador exacto, ordenados por suma de goles
    descendente (3-2 antes que 1-0); a igual diferencia, la suma es única
    por marcador, así que el ``groupby`` los deja contiguos. Los nombres
    conservan el orden de entrada (las vistas ya ordenan por nombre).
    ``points``/``chips`` los llena ``build_match_dialog_payload`` (necesita
    el marcador real).
    """
    ordered = sorted(rows, key=lambda r: r["home"] + r["away"], reverse=True)
    ordered = sorted(ordered, key=lambda r: r["home"] - r["away"],
                     reverse=True)
    groups = []
    for diff, diff_rows in groupby(
        ordered, key=lambda r: r["home"] - r["away"]
    ):
        subgroups = []
        for (home, away), sub_rows in groupby(
            diff_rows, key=lambda r: (r["home"], r["away"])
        ):
            names = [
                {"name": r["name"], "is_self": r["is_self"]}
                for r in sub_rows
            ]
            subgroups.append({"home": home, "away": away, "names": names,
                              "points": None, "chips": None})
        groups.append({"diff": diff, "subgroups": subgroups})
    return groups


def diff_label(diff: int, home: str, away: str) -> str:
    """Encabezado de grupo: '+N gol(es)' o 'Empate'.

    La bandera del equipo ganador la antepone el cliente (usa ``diff``);
    la CSS lo pasa a mayúsculas → '🏴 +2 GOLES'.
    """
    if diff == 0:
        return "Empate"
    team = home if diff > 0 else away
    n = abs(diff)
    unit = "gol" if n == 1 else "goles"
    return f"{team}  +{n} {unit}"


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
    if match.stage.is_group:
        return f"Grupo {match.home_team.group_name}"
    return match.name or match.stage.name


def _team_payload(team, placeholder: str) -> dict:
    if team is None:
        return {"name": placeholder, "placeholder": True}
    return {
        "name": team.name_es,
        "flag": static(team.flag_path) if team.flag_path else None,
        "fifa_code": team.fifa_code,
    }


def _match_payload(match: Match, finished: bool, can_record: bool) -> dict:
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
        "is_knockout": not match.stage.is_group,
        # Permiso + estado; el gate de 105 min lo calcula el JS al abrir
        # (un timing horneado al render se vuelve obsoleto) y el endpoint
        # revalida todo de cualquier forma.
        "can_record": can_record and not finished,
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
        for pred in predictions:
            rows_by_match[pred.match_id].append({
                "name": pred.user.first_name or pred.user.email,
                "home": pred.home_goals,
                "away": pred.away_goals,
                "is_self": pred.user_id == user.id,
            })

    records = user.can_record_results or user.is_superuser
    result = []
    for match in matches:
        finished = (
            match.status == "FINISHED"
            and match.home_goals is not None
            and match.away_goals is not None
        )
        payload = _match_payload(match, finished, records)
        if payload["revealed"]:
            is_draw = finished and match.home_goals == match.away_goals
            groups = group_predictions(rows_by_match.get(match.id, []))
            for group in groups:
                group["label"] = diff_label(
                    group["diff"],
                    payload["home"]["fifa_code"], payload["away"]["fifa_code"],
                )
                if not finished:
                    continue
                # Mismo marcador en todo el subgrupo: el desglose se
                # calcula una vez, no por persona.
                for sub in group["subgroups"]:
                    detail = score_detail(
                        sub["home"], sub["away"],
                        match.home_goals, match.away_goals,
                    )
                    sub["points"] = points_display(detail)
                    sub["chips"] = result_chips(detail, is_draw)
            payload["groups"] = groups
        result.append(payload)
    return result
