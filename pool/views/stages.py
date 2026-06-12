"""Vistas de predicción por fase del torneo (una página por Stage)."""

from collections import defaultdict
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from pool.models import Prediction, StageUser, User
from pool.services.match_dialog import build_match_dialog_payload
from pool.services.scoring import score_detail
from pool.services.standings import build_group_standings
from pool.utils import format_day, format_time
from tournament.models import Match, Stage, Team

# Ventana en la que un partido se considera "en juego". La app no es en
# tiempo real: el resultado aparece hasta que el sync lo marque FINISHED.
LIVE_WINDOW = timedelta(hours=2)


def _chip(label: str, value: int, state: str, icon: bool = False) -> dict:
    text = {"on": str(value), "off": "0", "na": "—"}[state]
    return {"label": label, "text": text, "state": state, "icon": icon}


def annotate_result(match: Match, prediction: Prediction | None) -> None:
    """Adjunta en memoria resultado final, puntos y chips del usuario.

    Para partidos terminados la tarjeta invierte la jerarquía: marcador
    real en las cajas (subrayado al ganador real vía ``home_mark``/
    ``away_mark``), predicción y desglose en la fila TÚ. ``points_kind``
    separa "sin predicción" (none) de "0 puntos" (zero).
    """
    match.is_finished = (
        match.status == "FINISHED"
        and match.home_goals is not None
        and match.away_goals is not None
    )
    now = timezone.now()
    match.is_live = (
        not match.is_finished
        and match.datetime <= now < match.datetime + LIVE_WINDOW
    )
    match.home_mark = match.away_mark = ""
    match.user_points = None
    match.points_kind = "none"
    match.chips = None
    if not match.is_finished:
        return

    is_draw = match.home_goals == match.away_goals
    if match.decided_by == Match.PENALTY_SHOOTOUT:
        # El marcador a 120' empata; el subrayado lo decide la tanda.
        home_wins = (
            (match.home_penalties or 0) > (match.away_penalties or 0)
        )
        marks = ("pick-win", "") if home_wins else ("", "pick-win")
        match.home_mark, match.away_mark = marks
    elif is_draw:
        match.home_mark = match.away_mark = "pick-tie"
    else:
        home_wins = match.home_goals > match.away_goals
        marks = ("pick-win", "") if home_wins else ("", "pick-win")
        match.home_mark, match.away_mark = marks

    if prediction is None:
        return
    detail = score_detail(
        prediction.home_goals, prediction.away_goals,
        match.home_goals, match.away_goals,
    )
    match.user_points = detail.points
    match.points_kind = "won" if detail.points else "zero"
    # Los chips suman exactamente el total; en empate real la diferencia
    # no aplica (na). El exacto incluye la diferencia, por eso enciende
    # también su chip.
    diff_on = detail.diff_bonus or (detail.exact and not is_draw)
    match.chips = [
        _chip("R", 3, "on" if detail.points else "off"),
        _chip("Dif", 1, "na" if is_draw else ("on" if diff_on else "off")),
        _chip("", 1, "on" if detail.exact else "off", icon=True),
    ]


def render_stage_sections(
    user: User, stage: Stage, by_date: bool = False
) -> list[dict]:
    """Devuelve las secciones de una fase listas para presentar.

    Fase de grupos: una sección por grupo (A→L), o por **día local de la
    sede** si ``by_date`` (la clave pasa a ser un ``date``; el orden del
    modelo es ``of_number``, por eso se fuerza cronológico). Eliminatoria:
    una sola sección (lista plana, equipos aún como placeholder). Cada
    sección es ``{"key", "label", "matches", "filled", "total", "points",
    "teams", "standings"}`` (``teams`` y ``standings`` solo agrupando por
    grupo: banderas del encabezado en el orden de la variante mix y
    tablas de posiciones en tres variantes), donde ``filled`` cuenta los
    partidos con predicción completa (una fila ``Prediction`` ya implica
    ambos marcadores) y ``points`` suma los puntos ya ganados en la
    sección. En cada partido
    adjunta en memoria día y hora **locales de la sede**
    (``Match.datetime`` está en UTC; se aplica ``Stadium.utc_offset``) y,
    si el usuario ya predijo, ``predicted_home``/``predicted_away``.
    ``select_related`` evita N+1.
    """
    matches = Match.objects.filter(stage=stage).select_related(
        "home_team", "away_team", "stadium", "stage"
    )
    if by_date:
        matches = matches.order_by("datetime", "of_number")
    # Materializado: el loop y build_group_standings deben compartir
    # instancias (y evita re-ejecutar el queryset).
    matches = list(matches)
    predictions = Prediction.objects.filter(user=user, match__stage=stage)
    preds_by_match = {p.match_id: p for p in predictions}

    is_group = stage.key == Stage.GROUP_STAGE
    SectionKey = str | date | None
    grouped: dict[SectionKey, list[Match]] = defaultdict(list)
    filled: dict[SectionKey, int] = defaultdict(int)
    points: dict[SectionKey, int] = defaultdict(int)
    teams: dict[SectionKey, dict[int, Team]] = defaultdict(dict)
    for match in matches:
        local_dt = match.datetime + timedelta(
            hours=match.stadium.utc_offset
        )
        match.local_day = format_day(local_dt)
        match.local_time = format_time(local_dt)
        if by_date:
            key = local_dt.date()
        else:
            key = match.home_team.group_name if is_group else None
        prediction = preds_by_match.get(match.id)
        if prediction is not None:
            match.predicted_home = prediction.home_goals
            match.predicted_away = prediction.away_goals
            filled[key] += 1
        annotate_result(match, prediction)
        if match.user_points is not None:
            points[key] += match.user_points
        grouped[key].append(match)
        # Equipos del grupo para el encabezado (sin query extra); por
        # fecha no aplica: serían hasta 12 banderas por día.
        if is_group and not by_date:
            for team in (match.home_team, match.away_team):
                if team is not None:
                    teams[key][team.id] = team

    standings = (
        build_group_standings(matches, preds_by_match)
        if is_group and not by_date else {}
    )
    keys = sorted(grouped) if is_group else list(grouped)
    return [
        {
            "key": key,
            "label": (
                grouped[key][0].local_day if by_date else f"Grupo {key}"
            ),
            "matches": grouped[key],
            "filled": filled[key],
            "total": len(grouped[key]),
            "points": points[key],
            "standings": standings.get(key),
            "teams": (
                standings[key].teams if key in standings
                else sorted(teams[key].values(), key=lambda t: t.name_es)
            ),
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
    by_date = (
        stage.key == Stage.GROUP_STAGE
        and request.GET.get("view") == "fecha"
    )
    sections = render_stage_sections(request.user, stage, by_date)
    flat_matches = [m for s in sections for m in s["matches"]]
    context = {
        "stage": stage,
        "state": stage_user.state,
        "can_edit": stage_user.can_edit,
        "sections": sections,
        "match_dialog_data": build_match_dialog_payload(
            flat_matches, request.user
        ),
        "is_group_stage": stage.key == Stage.GROUP_STAGE,
        "by_date": by_date,
        "tabs": _build_tabs(request.user),
        "deadline_iso": (
            stage.send_deadline.isoformat()
            if stage.send_deadline
            else ""
        ),
    }
    return render(request, "stage.html", context)

def reglas(request: HttpRequest) -> HttpResponse:
    return render(request, "reglas.html", {"tabs": _build_tabs(request.user)})