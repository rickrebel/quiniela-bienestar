"""Vistas de predicción por fase del torneo (una página por Stage)."""

from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from pool.models import Prediction, StageUser, User
from pool.utils import convert_date
from tournament.models import Match, Stage


def render_stage_matches(
    user: User, stage: Stage
) -> dict[str | None, list[Match]]:
    """Devuelve los partidos de una fase listos para presentar.

    Fase de grupos: dict ``{grupo: [matches]}`` ordenado A→L. Eliminatoria:
    ``{None: [matches]}`` (lista plana, equipos aún como placeholder). En
    cada partido adjunta en memoria la fecha formateada y, si el usuario ya
    predijo, ``predicted_home``/``predicted_away``. ``select_related`` evita
    N+1 en equipos y estadio.
    """
    matches = Match.objects.filter(stage=stage).select_related(
        "home_team", "away_team", "stadium"
    )
    predictions = Prediction.objects.filter(user=user, match__stage=stage)
    preds_by_match = {p.match_id: p for p in predictions}

    is_group = stage.key == Stage.GROUP_STAGE
    grouped: dict[str | None, list[Match]] = defaultdict(list)
    for match in matches:
        prediction = preds_by_match.get(match.id)
        if prediction is not None:
            match.predicted_home = prediction.home_goals
            match.predicted_away = prediction.away_goals
        match.formatted_date = convert_date(match.datetime)
        key = match.home_team.group_name if is_group else None
        grouped[key].append(match)

    if is_group:
        return dict(sorted(grouped.items()))
    return dict(grouped)


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
def etapa(request: HttpRequest, key: str) -> HttpResponse:
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
        "grouped": render_stage_matches(request.user, stage),
        "is_group_stage": stage.key == Stage.GROUP_STAGE,
        "tabs": _build_tabs(request.user),
        "deadline_iso": (
            stage.confirm_deadline.isoformat()
            if stage.confirm_deadline
            else ""
        ),
    }
    return render(request, "etapa.html", context)
