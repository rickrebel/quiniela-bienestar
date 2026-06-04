"""Vistas de predicción por fase del torneo (una página por Stage)."""

from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from pool.models import Prediction, StageUser, User
from pool.utils import format_day, format_time
from tournament.models import Match, Stage, Team


def render_stage_sections(user: User, stage: Stage) -> list[dict]:
    """Devuelve las secciones de una fase listas para presentar.

    Fase de grupos: una sección por grupo (A→L). Eliminatoria: una sola
    sección (lista plana, equipos aún como placeholder). Cada sección es
    ``{"key", "matches", "filled", "total", "teams"}`` (``teams`` solo en
    grupos, para las banderas del encabezado), donde ``filled`` cuenta los
    partidos con predicción completa (una fila ``Prediction`` ya implica
    ambos marcadores). En cada partido adjunta en memoria día y hora
    **locales de la sede** (``Match.datetime`` está en UTC; se aplica
    ``Stadium.utc_offset``) y, si el usuario ya predijo,
    ``predicted_home``/``predicted_away``. ``select_related`` evita N+1.
    """
    matches = Match.objects.filter(stage=stage).select_related(
        "home_team", "away_team", "stadium"
    )
    predictions = Prediction.objects.filter(user=user, match__stage=stage)
    preds_by_match = {p.match_id: p for p in predictions}

    is_group = stage.key == Stage.GROUP_STAGE
    grouped: dict[str | None, list[Match]] = defaultdict(list)
    filled: dict[str | None, int] = defaultdict(int)
    teams: dict[str | None, dict[int, Team]] = defaultdict(dict)
    for match in matches:
        key = match.home_team.group_name if is_group else None
        prediction = preds_by_match.get(match.id)
        if prediction is not None:
            match.predicted_home = prediction.home_goals
            match.predicted_away = prediction.away_goals
            filled[key] += 1
        local_dt = match.datetime + timedelta(
            hours=match.stadium.utc_offset
        )
        match.local_day = format_day(local_dt)
        match.local_time = format_time(local_dt)
        grouped[key].append(match)
        if is_group:  # equipos del grupo para el encabezado (sin query extra)
            for team in (match.home_team, match.away_team):
                if team is not None:
                    teams[key][team.id] = team

    keys = sorted(grouped) if is_group else list(grouped)
    return [
        {
            "key": key,
            "matches": grouped[key],
            "filled": filled[key],
            "total": len(grouped[key]),
            "teams": sorted(teams[key].values(), key=lambda t: t.name_es),
        }
        for key in keys
    ]


def _build_tabs(user: User) -> list[dict]:
    """Arma los tabs: una fase por entrada, con su estado para el usuario.

    Para fases sin ``StageUser`` aún se usa una instancia transitoria (no
    guardada) solo para derivar ``state``; no escribe en la base.
    """
    states = {
        su.stage_id: su
        for su in StageUser.objects.select_related("stage").filter(user=user)
    }
    tabs = []
    for stage in Stage.objects.all():
        stage_user = states.get(stage.id) or StageUser(
            user=user, stage=stage
        )
        tabs.append({"stage": stage, "state": stage_user.state})
    return tabs


@login_required
def stage_view(request: HttpRequest, key: str) -> HttpResponse:
    """Renderiza la página de una fase con el estado del usuario.

    ``get_or_create`` del ``StageUser`` blinda el caso de usuarios sin la
    fila (creación perezosa, además del backfill por comando).
    """
    stage = get_object_or_404(Stage, key=key)
    stage_user, _ = StageUser.objects.select_related("stage").get_or_create(
        user=request.user, stage=stage
    )
    context = {
        "stage": stage,
        "state": stage_user.state,
        "can_edit": stage_user.can_edit,
        "sections": render_stage_sections(request.user, stage),
        "is_group_stage": stage.key == Stage.GROUP_STAGE,
        "tabs": _build_tabs(request.user),
        "deadline_iso": (
            stage.send_deadline.isoformat()
            if stage.send_deadline
            else ""
        ),
    }
    return render(request, "stage.html", context)
