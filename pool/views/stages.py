"""Vistas de predicción por fase del torneo (una página por Stage)."""

import re
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from pool.models import Prediction, StageUser, User
from pool.services.match_dialog import build_match_dialog_payload
from pool.services.scoring import result_chips, score_detail
from pool.services.standings import build_group_standings
from pool.utils import format_day, format_long_day, format_time
from tournament.models import Match, Stage, Team

# Ventana en la que un partido se considera "en juego". La app no es en
# tiempo real: el resultado aparece hasta que el sync lo marque FINISHED.
LIVE_WINDOW = timedelta(hours=2)


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
    match.chips = result_chips(detail, is_draw)


def render_stage_sections(user: User, stage: Stage) -> list[dict]:
    """Devuelve las secciones de una fase listas para presentar.

    Fase de grupos: una sección por grupo (A→L). Eliminatoria: una sola
    sección (lista plana, equipos aún como placeholder). Cada sección es
    ``{"key", "label", "matches", "filled", "total", "points",
    "teams", "standings"}`` (``teams`` y ``standings`` solo agrupando por
    grupo: banderas del encabezado en el orden de la variante mix y tablas
    de posiciones en tres variantes), donde ``filled`` cuenta los partidos
    con predicción completa (una fila ``Prediction`` ya implica ambos
    marcadores) y ``points`` suma los puntos ya ganados en la sección. En
    cada partido adjunta en memoria día y hora **locales de la sede**
    (``Match.datetime`` está en UTC; se aplica ``Stadium.utc_offset``) y,
    si el usuario ya predijo, ``predicted_home``/``predicted_away``.
    ``select_related`` evita N+1.
    """
    # Materializado: el loop y build_group_standings deben compartir
    # instancias (y evita re-ejecutar el queryset).
    matches = list(
        Match.objects.filter(stage=stage).select_related(
            "home_team", "away_team", "stadium", "stage"
        )
    )
    predictions = Prediction.objects.filter(user=user, match__stage=stage)
    preds_by_match = {p.match_id: p for p in predictions}
    return _build_sections(matches, preds_by_match, stage.is_group)


def render_group_sections(user: User) -> list[dict]:
    """Secciones de la sombrilla de grupos (las 3 sub-fases juntas).

    A diferencia de ``render_stage_sections`` (una sub-fase), carga TODOS
    los partidos ``stage__is_group=True`` para que la tabla de posiciones
    sea **acumulada** sobre las 3 jornadas. La editabilidad por partido la
    decide la vista (``groups_view``), no esta función.
    """
    matches = list(
        Match.objects.filter(stage__is_group=True).select_related(
            "home_team", "away_team", "stadium", "stage"
        )
    )
    preds_by_match = {
        p.match_id: p
        for p in Prediction.objects.filter(
            user=user, match__stage__is_group=True
        )
    }
    return _build_sections(matches, preds_by_match, True)


def _build_sections(
    matches: list[Match],
    preds_by_match: dict[int, Prediction],
    is_group: bool,
) -> list[dict]:
    """Arma las secciones a partir de partidos ya cargados y predicciones.

    Núcleo compartido por ``render_stage_sections`` (una fase) y
    ``render_group_sections`` (sombrilla de grupos): agrupa, adjunta día/
    hora locales y resultado en memoria, y calcula tablas de posiciones.
    """
    SectionKey = str | None
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
        # Equipos del grupo para el encabezado (sin query extra).
        if is_group:
            for team in (match.home_team, match.away_team):
                if team is not None:
                    teams[key][team.id] = team

    standings = (
        build_group_standings(matches, preds_by_match) if is_group else {}
    )
    keys = sorted(grouped) if is_group else list(grouped)
    return [
        {
            "key": key,
            "label": f"Grupo {key}",
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


# Placeholder de posición de grupo en eliminatoria: "1A", "2B". Los
# terceros ("3A/B/C/D/F") y ganadores ("W74") no son resolubles aquí.
GROUP_POS_RE = re.compile(r"^([12])([A-L])$")
VARIANTS = ("est", "mix", "real")


def resolve_variant(value: str | None) -> str:
    """Normaliza la variante de la querystring; mix por defecto."""
    return value if value in VARIANTS else "mix"


def resolve_group_placeholders(user: User, variant: str) -> dict[str, "Team"]:
    """Mapa de placeholder de posición de grupo ('1A','2B') → equipo.

    Resuelve 1.º/2.º de cada grupo según la variante elegida, reusando las
    posiciones que ya calcula ``build_group_standings``. En 'real' solo
    incluye grupos cerrados (6 partidos FINISHED): el resto queda sin
    resolver para que la tarjeta muestre el placeholder textual.
    """
    group_matches = list(
        Match.objects.filter(stage__is_group=True).select_related(
            "home_team", "away_team", "stadium", "stage"
        )
    )
    preds = {
        p.match_id: p
        for p in Prediction.objects.filter(
            user=user, match__stage__is_group=True
        )
    }
    standings = build_group_standings(group_matches, preds)

    finished: dict[str, int] = defaultdict(int)
    for m in group_matches:
        if (
            m.status == "FINISHED"
            and m.home_goals is not None
            and m.away_goals is not None
            and m.home_team is not None
        ):
            finished[m.home_team.group_name] += 1

    resolved: dict[str, Team] = {}
    for group, gs in standings.items():
        if variant == "real" and finished[group] < 6:
            continue
        table = next(t for t in gs.tables if t.variant == variant)
        for pos, row in enumerate(table.rows[:2], start=1):
            resolved[f"{pos}{group}"] = row.team
    return resolved


def _build_tabs(user: User) -> list[dict]:
    """Arma los tabs (uno por fase visible), en orden de torneo.

    Las 3 sub-fases ``is_group`` se colapsan en un único tab "Grupos" que
    enlaza al alias ``/stage/grupos/``. Cada tab es ``{"key", "short_name"}``
    (``key`` "grupos" para el bloque de grupos).
    """
    tabs: list[dict] = []
    group_done = False
    for stage in Stage.objects.all():
        if stage.is_group:
            if group_done:
                continue
            group_done = True
            tabs.append({"key": "grupos", "short_name": "Grupos"})
        else:
            tabs.append(
                {"key": stage.key, "short_name": stage.short_name}
            )
    return tabs


def current_group_stage(user: User) -> StageUser:
    """``StageUser`` de la sub-fase de grupos vigente para el usuario.

    Vigente = la sub-fase ``is_group`` abierta y sin vencer, de menor
    ``order`` (la jornada en captura). Si ninguna está abierta, cae a la
    primera no enviada (encabezado en solo lectura) o, en su defecto, a la
    última. Igual que las vistas, materializa al vuelo un ``StageUser`` si
    el usuario aún no tiene la fila.
    """
    substages = list(Stage.objects.filter(is_group=True))
    states = {
        su.stage_id: su
        for su in StageUser.objects.select_related("stage").filter(
            user=user, stage__is_group=True
        )
    }

    def su_for(stage: Stage) -> StageUser:
        return states.get(stage.id) or StageUser(user=user, stage=stage)

    for stage in substages:
        if stage.is_open and not stage.is_past_deadline:
            return su_for(stage)
    for stage in substages:
        su = su_for(stage)
        if su.state != StageUser.SENT:
            return su
    return su_for(substages[-1])


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
    sections = render_stage_sections(request.user, stage)
    flat_matches = [m for s in sections for m in s["matches"]]

    # En eliminatoria, rellenar en memoria los equipos de primera ronda
    # (placeholders "1A"/"2B") según la variante elegida; las tarjetas y el
    # dialog comparten estas instancias. Terceros y ganadores quedan como
    # placeholder textual.
    is_group_stage = stage.is_group
    variant = resolve_variant(request.GET.get("variant"))
    derivable = False
    if not is_group_stage:
        resolved = resolve_group_placeholders(request.user, variant)
        for m in flat_matches:
            if GROUP_POS_RE.match(m.home_placeholder or ""):
                derivable = True
                if m.home_team is None:
                    m.home_team = resolved.get(m.home_placeholder)
            if GROUP_POS_RE.match(m.away_placeholder or ""):
                derivable = True
                if m.away_team is None:
                    m.away_team = resolved.get(m.away_placeholder)

    for m in flat_matches:
        m.editable = stage_user.can_edit

    context = {
        "stage": stage,
        "state": stage_user.state,
        "can_edit": stage_user.can_edit,
        "sections": sections,
        "match_dialog_data": build_match_dialog_payload(
            flat_matches, request.user
        ),
        "is_group_stage": is_group_stage,
        "variant": variant,
        "derivable": derivable,
        "tabs": _build_tabs(request.user),
        "tabs_active": stage.key,
        "deadline_iso": (
            stage.send_deadline.isoformat()
            if stage.send_deadline
            else ""
        ),
    }
    return render(request, "stage.html", context)


@login_required
def groups_view(request: HttpRequest) -> HttpResponse:
    """Pestaña unificada de Grupos sobre las 3 sub-fases (``is_group``).

    Muestra todos los grupos A–L con la tabla de posiciones **acumulada**,
    pero solo los partidos de la sub-fase vigente son editables; el resto
    se ve en solo lectura. "Enviar" finaliza únicamente esa sub-fase: el
    contexto (``stage``/``state``/``deadline_iso``) apunta a la vigente, y
    su ``key`` viaja en ``data-stage`` para que ``/send/`` cierre la
    jornada correcta.
    """
    active = current_group_stage(request.user)
    stage = active.stage
    sections = render_group_sections(request.user)
    flat_matches = [m for s in sections for m in s["matches"]]
    for m in flat_matches:
        m.editable = m.stage_id == active.stage_id and active.can_edit

    context = {
        "stage": stage,
        "state": active.state,
        "can_edit": active.can_edit,
        "sections": sections,
        "match_dialog_data": build_match_dialog_payload(
            flat_matches, request.user
        ),
        "is_group_stage": True,
        "variant": resolve_variant(request.GET.get("variant")),
        "derivable": False,
        "tabs": _build_tabs(request.user),
        "tabs_active": "grupos",
        "deadline_iso": (
            stage.send_deadline.isoformat()
            if stage.send_deadline
            else ""
        ),
    }
    return render(request, "stage.html", context)


@login_required
def por_fecha_view(request: HttpRequest) -> HttpResponse:
    """Calendario global de solo lectura: todos los partidos por fase.

    Doble agrupación: las fases van en orden de creación (= progresión del
    torneo) y, dentro de cada una, los partidos se agrupan por **fecha
    local de la sede** (con día de la semana). El queryset ya viene
    ordenado por ``(stage_id, datetime, of_number)``, así que ambos cortes
    son lineales. Reusa ``annotate_result`` y el dialog de detalle. No
    edita: las tarjetas se renderizan sin ``can_edit``.
    """
    matches = list(
        Match.objects.select_related(
            "home_team", "away_team", "stadium", "stage"
        ).order_by("stage_id", "datetime", "of_number")
    )
    preds = {
        p.match_id: p
        for p in Prediction.objects.filter(user=request.user)
    }
    sections: list[dict] = []
    section: dict | None = None
    date_group: dict | None = None
    for match in matches:
        local_dt = match.datetime + timedelta(
            hours=match.stadium.utc_offset
        )
        match.local_day = format_day(local_dt)
        match.local_time = format_time(local_dt)
        match.is_group = match.stage.is_group
        prediction = preds.get(match.id)
        if prediction is not None:
            match.predicted_home = prediction.home_goals
            match.predicted_away = prediction.away_goals
        annotate_result(match, prediction)
        if section is None or section["stage_id"] != match.stage_id:
            section = {
                "stage_id": match.stage_id,
                "label": match.stage.name,
                "date_groups": [],
            }
            sections.append(section)
            date_group = None
        local_date = local_dt.date()
        if date_group is None or date_group["date"] != local_date:
            date_group = {
                "date": local_date,
                "label": format_long_day(local_dt),
                "matches": [],
                "points": 0,
                "finished": 0,
            }
            section["date_groups"].append(date_group)
        date_group["matches"].append(match)
        # Puntos ganados ese día (mismo lenguaje que el header de grupos:
        # total en dorado a la derecha cuando ya hay partidos terminados).
        if match.is_finished:
            date_group["finished"] += 1
            date_group["points"] += match.user_points or 0

    context = {
        "sections": sections,
        "match_dialog_data": build_match_dialog_payload(
            matches, request.user
        ),
        "tabs": _build_tabs(request.user),
    }
    return render(request, "por_fecha.html", context)


def reglas(request: HttpRequest) -> HttpResponse:
    return render(request, "reglas.html", {"tabs": _build_tabs(request.user)})