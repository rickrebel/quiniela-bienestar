"""Vistas de predicción por fase del torneo (una página por Stage)."""

import re
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone

from pool.models import Prediction, Quiniela, User, Window, WindowUser
from pool.services import anexo_c
from pool.services.bracket import resolve_sources
from pool.services.anexo_c import assign_thirds
from pool.services.match_dialog import build_match_dialog_payload
from pool.services.scoring import chips_from_codes
from pool.services.standings import build_group_standings
from pool.services.thirds import build_thirds
from pool.utils import format_day, format_long_day, format_time
from pool.views.scope import with_quiniela
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
    # Equipo que el usuario cree que avanza por penales (solo si predijo
    # empate en eliminatoria); la tarjeta lo muestra a todos, con o sin la
    # regla activa en la quiniela.
    match.predicted_advancing_id = (
        prediction.advancing_team_id if prediction else None
    )
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

    # Lee lo congelado por la evaluación; points None = aún sin evaluar.
    if prediction is None or prediction.points is None:
        return
    codes = [rule.code for rule in prediction.rules.all()]
    match.user_points = prediction.points
    match.points_kind = "won" if prediction.points else "zero"
    show_penalty = match.decided_by == Match.PENALTY_SHOOTOUT
    match.chips = chips_from_codes(codes, is_draw, show_penalty)


def render_window_sections(
    user: User, quiniela: Quiniela, stages: list[Stage], is_group: bool,
    attach_standings: bool = True,
) -> list[dict]:
    """Secciones de una ventana (sus 1+ fases) listas para presentar.

    Carga los partidos de ``stages`` (una fase de eliminatoria o las 3 de
    grupos concentrados) y las predicciones del usuario **en esta
    quiniela**. Cada sección es ``{"key", "label", "matches", "filled",
    "total", "points", "teams", "standings"}`` (``teams``/``standings``
    solo agrupando por grupo). En cada partido adjunta en memoria día/hora
    locales de la sede y, si predijo, ``predicted_home``/``predicted_away``.
    ``select_related`` evita N+1. ``attach_standings=False`` deja las
    posiciones en ``None`` (la vista de grupos las sustituye por la tabla
    acumulada sobre las 3 jornadas).
    """
    # Materializado: el loop y build_group_standings deben compartir
    # instancias (y evita re-ejecutar el queryset).
    matches = list(
        Match.objects.filter(stage__in=stages).select_related(
            "home_team", "away_team", "stadium", "stage"
        )
    )
    predictions = (
        Prediction.objects.filter(
            user=user, quiniela=quiniela, match__stage__in=stages)
        .prefetch_related("rules")
    )
    preds_by_match = {p.match_id: p for p in predictions}
    return _build_sections(
        matches, preds_by_match, is_group, attach_standings)


def _build_sections(
    matches: list[Match],
    preds_by_match: dict[int, Prediction],
    is_group: bool,
    attach_standings: bool = True,
) -> list[dict]:
    """Arma las secciones a partir de partidos ya cargados y predicciones.

    Agrupa por grupo (en grupos) o en una sección plana (eliminatoria),
    adjunta día/hora locales y resultado en memoria, y calcula las tablas
    de posiciones (salvo ``attach_standings=False``).
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
        build_group_standings(matches, preds_by_match)
        if is_group and attach_standings else {}
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


# Placeholder de posición de grupo en eliminatoria: "1A", "2B". El tercero
# ("3A/B/C/D/F") se resuelve aparte vía anexo C; los ganadores/perdedores
# ("W74"/"L101") en ``services/bracket.py`` (ganador real o contendientes).
GROUP_POS_RE = re.compile(r"^([12])([A-L])$")
THIRD_RE = re.compile(r"^3[A-L](/[A-L])+$")
VARIANTS = ("est", "mix", "real")
ALL_GROUPS = "ABCDEFGHIJKL"


def resolve_variant(value: str | None) -> str:
    """Normaliza la variante de la querystring; mix por defecto."""
    return value if value in VARIANTS else "mix"


def _load_group_standings(user: User, quiniela: Quiniela):
    """Carga partidos de grupos y sus tablas de posiciones (dos queries).

    Tabla **acumulada** sobre las 3 jornadas (verdad del torneo),
    independiente de la ventana; las variantes ``est``/``mix`` usan las
    predicciones del usuario **en esta quiniela**. Compartido por la
    resolución de placeholders ('1A'/'2B'), los terceros del anexo C y la
    tabla que la vista de grupos cuelga en cada sección.
    """
    group_matches = list(
        Match.objects.filter(stage__is_group=True).select_related(
            "home_team", "away_team", "stadium", "stage"
        )
    )
    preds = {
        p.match_id: p
        for p in Prediction.objects.filter(
            user=user, quiniela=quiniela, match__stage__is_group=True
        )
    }
    return group_matches, build_group_standings(group_matches, preds)


@login_required
@with_quiniela
def group_standings(request: HttpRequest) -> HttpResponse:
    """Fragmento HTML de la tabla de un grupo, recalculada desde la BD
    actual. Lo pide el autosave (``submit.js``) para refrescar en vivo las
    variantes ``est``/``mix`` tras guardar una predicción, sin recargar."""
    group = request.GET.get("group", "")
    if group not in ALL_GROUPS:
        return HttpResponseBadRequest("grupo inválido")
    _, standings = _load_group_standings(request.user, request.quiniela)
    gs = standings.get(group)
    if gs is None:
        return HttpResponseBadRequest("grupo sin datos")
    return render(
        request,
        "_group_standings_fragment.html",
        {"standings": gs, "teams": gs.teams},
    )


def _finished_per_group(group_matches: list[Match]) -> dict[str, int]:
    finished: dict[str, int] = defaultdict(int)
    for m in group_matches:
        if (
            m.status == "FINISHED"
            and m.home_goals is not None
            and m.away_goals is not None
            and m.home_team is not None
        ):
            finished[m.home_team.group_name] += 1
    return finished


def _group_placeholders(
    standings: dict, finished: dict[str, int], variant: str
) -> dict[str, Team]:
    """Mapa de placeholder de posición ('1A','2B') → equipo según la variante.
    En 'real' solo incluye grupos cerrados (6 FINISHED); el resto queda sin
    resolver para que la tarjeta muestre el placeholder textual."""
    resolved: dict[str, Team] = {}
    for group, gs in standings.items():
        if variant == "real" and finished[group] < 6:
            continue
        table = next(t for t in gs.tables if t.variant == variant)
        for pos, row in enumerate(table.rows[:2], start=1):
            resolved[f"{pos}{group}"] = row.team
    return resolved


def _third_placeholders(
    thirds: list, finished: dict[str, int], variant: str,
    matches: list[Match],
) -> dict[int, Team]:
    """Mapa ``match_id`` → tercero visitante para los dieciseisavos, según el
    anexo C. La clave del partido es su ganador local ('1I' → 'I'); el anexo
    dice qué grupo aporta el tercero. En 'real' solo resuelve si los 12
    grupos están cerrados (de lo contrario los 8 terceros no son firmes)."""
    if variant == "real" and any(finished[g] < 6 for g in ALL_GROUPS):
        return {}
    mapping = assign_thirds({t.group for t in thirds if t.qualified})
    if mapping is None:
        return {}
    third_team = {t.group: t.team for t in thirds}
    resolved: dict[int, Team] = {}
    for m in matches:
        if not THIRD_RE.match(m.away_placeholder or ""):
            continue
        third_group = mapping.get((m.home_placeholder or "")[1:])
        if third_group:
            resolved[m.id] = third_team.get(third_group)
    return resolved


def _build_thirds_simulator(
    thirds: list, flat_matches: list[Match]
) -> dict:
    """Payload del simulador "¿qué pasaría si...?" de dieciseisavos.

    El cliente (``thirds_sim.js``) replica el lookup del anexo C para que el
    usuario explore cortes alternativos de los 8 mejores terceros sin recargar.
    De paso fija ``ThirdRow.match_number`` del cruce por defecto (los 8
    clasificados) para que la columna "No." salga ya pintada. ``flag_url`` se
    resuelve aquí porque el JS no puede invocar ``{% static %}``.
    """
    sim_matches = [
        {
            "match_id": m.id,
            "number": m.of_number,
            "winner_group": (m.home_placeholder or "")[1:],
            "away_placeholder": m.away_placeholder,
        }
        for m in flat_matches
        if THIRD_RE.match(m.away_placeholder or "")
    ]

    mapping = assign_thirds({t.group for t in thirds if t.qualified})
    if mapping is not None:
        # Invertir el cruce (grupo del tercero -> No. de partido del ganador).
        number_by_third = {
            mapping[sm["winner_group"]]: sm["number"]
            for sm in sim_matches
            if sm["winner_group"] in mapping
        }
        for t in thirds:
            if t.qualified:
                t.match_number = number_by_third.get(t.group)

    return {
        "winner_slots": anexo_c.WINNER_SLOTS,
        "combinations": anexo_c.COMBINATIONS,
        "thirds": [
            {
                "group": t.group,
                "name": t.team.name_es,
                "flag_url": (
                    static(t.team.flag_path) if t.team.flag_path else ""
                ),
                "qualified": t.qualified,
            }
            for t in thirds
        ],
        "matches": sim_matches,
    }


def _is_group_window(window: Window) -> bool:
    """True si la ventana agrupa solo fases de grupo (``is_group``)."""
    stages = list(window.stages.all())
    return bool(stages) and all(s.is_group for s in stages)


def _build_tabs(quiniela: Quiniela) -> list[dict]:
    """Tabs de la quiniela, en orden, con los grupos colapsados en uno.

    El tab es una unidad de **presentación**, no de envío: todas las
    ventanas ``is_group`` (1 en sanginiela, 3 en bienestar) se colapsan en
    un único tab "Grupos" (``key="grupos"``, ``is_groups=True`` → ruta
    ``groups``). Cada ventana de eliminatoria queda 1:1 (``key=str(order)``,
    ``is_groups=False`` → ruta ``window``). ``key`` se compara contra
    ``tabs_active`` para marcar el activo.
    """
    tabs: list[dict] = []
    grupos_emitted = False
    for w in quiniela.windows.prefetch_related("stages").order_by("order"):
        if _is_group_window(w):
            if not grupos_emitted:
                tabs.append({
                    "key": "grupos",
                    "short_name": "Grupos",
                    "is_groups": True,
                })
                grupos_emitted = True
            continue
        tabs.append({
            "key": str(w.order),
            "short_name": w.resolved_short_name(),
            "is_groups": False,
        })
    return tabs


def _opens_at_label(window: Window) -> str:
    """Etiqueta local de apertura del envío para el aviso de UPCOMING.

    Vacía si la ventana aún no fija ``opens_at`` (el aviso cae entonces a
    "se habilitará pronto"). ``opens_at`` es UTC; se convierte a hora local
    del sitio antes de formatear.
    """
    opens_at = window.resolved_opens_at()
    if opens_at is None:
        return ""
    local = timezone.localtime(opens_at)
    return f"{format_long_day(local)}, {format_time(local)}"


@login_required
@with_quiniela
def window_view(request: HttpRequest, order: int) -> HttpResponse:
    """Página de una ventana de predicción (1+ fases) de la quiniela.

    Generaliza las antiguas ``groups_view`` (3 sub-fases) y ``stage_view``
    (una fase): tabs, editabilidad y envío son **por ventana** (un
    ``WindowUser``); todas las tarjetas comparten su estado. En ventanas de
    grupo la tabla de posiciones es acumulada sobre las 3 jornadas; en
    eliminatoria se resuelven los placeholders 1A/2B y los terceros del
    anexo C como antes (estructura del torneo, intacta).
    """
    quiniela = request.quiniela
    window = get_object_or_404(
        Window.objects.prefetch_related("stages"),
        quiniela=quiniela, order=order,
    )
    stages = list(window.stages.all())
    is_group_window = bool(stages) and all(s.is_group for s in stages)
    # Los grupos viven en su tab único canónico (``groups_view``), que
    # colapsa las 1+ ventanas is_group; no se entra por ``order``.
    if is_group_window:
        return redirect("groups", quiniela.slug)
    window_user, _ = WindowUser.objects.get_or_create(
        user=request.user, window=window)

    # Las posiciones se cuelgan aparte (acumuladas), así que las secciones
    # se arman sin ellas.
    sections = render_window_sections(
        request.user, quiniela, stages, is_group_window,
        attach_standings=False,
    )
    flat_matches = [m for s in sections for m in s["matches"]]

    # La editabilidad de un cruce exige contendientes reales (equipos ya
    # definidos en BD), no la resolución en memoria por variante: se captura
    # antes de que el rellenado estimado sobrescriba equipos nulos.
    for m in flat_matches:
        m._real_teams = (
            m.home_team_id is not None and m.away_team_id is not None
        )

    variant = resolve_variant(request.GET.get("variant"))
    derivable = False
    thirds = None
    thirds_sim = None
    if is_group_window:
        # Tabla acumulada sobre las 3 jornadas, no solo las de esta ventana.
        _, standings = _load_group_standings(request.user, quiniela)
        for section in sections:
            gs = standings.get(section["key"])
            if gs is not None:
                section["standings"] = gs
                section["teams"] = gs.teams
    else:
        # Eliminatoria: rellenar en memoria los equipos de primera ronda
        # (placeholders "1A"/"2B" y, en dieciseisavos, el tercero del anexo
        # C) según la variante; tarjetas y dialog comparten instancias.
        stage = stages[0]
        group_matches, standings = _load_group_standings(
            request.user, quiniela)
        finished = _finished_per_group(group_matches)
        resolved = _group_placeholders(standings, finished, variant)
        for m in flat_matches:
            if GROUP_POS_RE.match(m.home_placeholder or ""):
                derivable = True
                if m.home_team is None:
                    m.home_team = resolved.get(m.home_placeholder)
            if GROUP_POS_RE.match(m.away_placeholder or ""):
                derivable = True
                if m.away_team is None:
                    m.away_team = resolved.get(m.away_placeholder)
        if stage.key == "LAST_32":
            thirds = build_thirds(standings)[variant]
            third_teams = _third_placeholders(
                thirds, finished, variant, flat_matches
            )
            for m in flat_matches:
                if THIRD_RE.match(m.away_placeholder or ""):
                    derivable = True
                    if m.away_team is None:
                        m.away_team = third_teams.get(m.id)
            thirds_sim = _build_thirds_simulator(thirds, flat_matches)
        # Octavos en adelante: ganador real o contendientes del cruce
        # origen ("W74"/"L101"). No-op en LAST_32 (placeholders de grupo).
        resolve_sources(flat_matches, request.user, quiniela)

    for m in flat_matches:
        m.editable = (
            window_user.can_edit and not m.has_started and m._real_teams
        )

    deadline = window.resolved_send_deadline()
    context = {
        "window": window,
        # Solo para el match-card (``stage.key == 'FINAL'``); en ventanas de
        # grupo no se usa (is_group_stage corta antes).
        "stage": stages[0],
        "state": window_user.state,
        "can_edit": window_user.can_edit,
        "opens_at_label": _opens_at_label(window),
        "sections": sections,
        "match_dialog_data": build_match_dialog_payload(
            flat_matches, request.user, quiniela
        ),
        "is_group_stage": is_group_window,
        "variant": variant,
        "derivable": derivable,
        "thirds": thirds,
        "thirds_sim": thirds_sim,
        "tabs": _build_tabs(quiniela),
        "tabs_active": str(window.order),
        "deadline_iso": deadline.isoformat() if deadline else "",
    }
    return render(request, "stage.html", context)


def _active_group_window(
    user: User, quiniela: Quiniela, group_windows: list[Window]
) -> tuple[Window, WindowUser]:
    """Ventana de grupo vigente y su ``WindowUser`` para el usuario.

    Vigente = la ventana ``is_group`` abierta y sin vencer de menor
    ``order`` (la jornada en captura). Si ninguna está abierta, la primera
    no enviada (encabezado en solo lectura) o, en su defecto, la última.
    Materializa el ``WindowUser`` perezosamente. Generaliza a 1 ventana
    (sanginiela: grupos concentrados, siempre la activa) o N (bienestar:
    una por jornada). ``group_windows`` debe venir ordenado por ``order``.
    """
    states = {
        wu.window_id: wu
        for wu in WindowUser.objects.filter(
            user=user, window__in=group_windows)
    }

    def wu_for(window: Window) -> WindowUser:
        wu = states.get(window.id)
        if wu is None:
            wu, _ = WindowUser.objects.get_or_create(user=user, window=window)
            states[window.id] = wu
        return wu

    for window in group_windows:
        if window.is_open and not window.is_past_deadline:
            return window, wu_for(window)
    for window in group_windows:
        wu = wu_for(window)
        if wu.state != WindowUser.SENT:
            return window, wu
    last = group_windows[-1]
    return last, wu_for(last)


@login_required
@with_quiniela
def groups_view(request: HttpRequest) -> HttpResponse:
    """Tab único de Grupos sobre las ventanas ``is_group`` de la quiniela.

    Muestra los 12 grupos A–L con la tabla de posiciones **acumulada**,
    pero solo los partidos de la ventana (jornada) vigente son editables;
    el resto en solo lectura. "Enviar" finaliza únicamente esa ventana: el
    contexto (``window``/``state``/``deadline``) apunta a la vigente y su
    ``order`` viaja en ``.content[data-window]`` para que ``/send/`` cierre
    la jornada correcta. Generaliza a 1 ventana (sanginiela) o N
    (bienestar). Desacopla el tab (presentación) de la ventana (envío).
    """
    quiniela = request.quiniela
    group_windows = [
        w for w in quiniela.windows.prefetch_related("stages").order_by("order")
        if _is_group_window(w)
    ]
    if not group_windows:
        raise Http404("La quiniela no tiene ventanas de grupo.")
    active_window, active_wu = _active_group_window(
        request.user, quiniela, group_windows)

    group_stages = [s for w in group_windows for s in w.stages.all()]
    sections = render_window_sections(
        request.user, quiniela, group_stages, is_group=True,
        attach_standings=False,
    )
    flat_matches = [m for s in sections for m in s["matches"]]

    # Tabla acumulada sobre las 3 jornadas, no solo la ventana activa.
    _, standings = _load_group_standings(request.user, quiniela)
    for section in sections:
        gs = standings.get(section["key"])
        if gs is not None:
            section["standings"] = gs
            section["teams"] = gs.teams

    # Editabilidad por partido: solo la jornada (ventana) vigente.
    active_stage_ids = {s.id for s in active_window.stages.all()}
    for m in flat_matches:
        m.editable = (
            m.stage_id in active_stage_ids
            and active_wu.can_edit
            and not m.has_started
        )

    deadline = active_window.resolved_send_deadline()
    context = {
        "window": active_window,
        "stage": group_stages[0],
        "state": active_wu.state,
        "can_edit": active_wu.can_edit,
        "opens_at_label": _opens_at_label(active_window),
        "sections": sections,
        "match_dialog_data": build_match_dialog_payload(
            flat_matches, request.user, quiniela
        ),
        "is_group_stage": True,
        "variant": resolve_variant(request.GET.get("variant")),
        "derivable": False,
        "thirds": None,
        "thirds_sim": None,
        "tabs": _build_tabs(quiniela),
        "tabs_active": "grupos",
        "deadline_iso": deadline.isoformat() if deadline else "",
    }
    return render(request, "stage.html", context)


@login_required
@with_quiniela
def por_fecha_view(request: HttpRequest) -> HttpResponse:
    """Calendario global de solo lectura: todos los partidos por fase.

    Doble agrupación: las fases van en orden de torneo (``Stage.order``) y,
    dentro de cada una, los partidos se agrupan por **fecha local de la
    sede** (con día de la semana). El queryset ya viene ordenado por
    ``(stage__order, datetime, of_number)``, así que ambos cortes son
    lineales. Reusa ``annotate_result`` y el dialog de detalle. No edita:
    las tarjetas se renderizan sin ``can_edit``.
    """
    matches = list(
        Match.objects.select_related(
            "home_team", "away_team", "stadium", "stage"
        ).order_by("stage__order", "datetime", "of_number")
    )
    preds = {
        p.match_id: p
        for p in Prediction.objects.filter(
            user=request.user, quiniela=request.quiniela
        ).prefetch_related("rules")
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

    # Ganador/contendientes del cruce origen, reutilizando los partidos y
    # predicciones ya cargados (sin queries extra).
    resolve_sources(
        matches, request.user, request.quiniela,
        source_by_number={m.of_number: m for m in matches},
        preds_by_match=preds,
    )

    # Día al que la página hace scroll automático: el de hoy; si hoy no hay
    # partidos, el próximo día con partidos; si todo quedó en el pasado, el
    # último. Marca un solo date_group (ancla en el template).
    today = timezone.localdate()
    all_groups = [g for s in sections for g in s["date_groups"]]
    target = next((g for g in all_groups if g["date"] == today), None)
    if target is None:
        target = next((g for g in all_groups if g["date"] > today), None)
    if target is None and all_groups:
        target = all_groups[-1]
    if target is not None:
        target["is_today"] = True

    context = {
        "sections": sections,
        "match_dialog_data": build_match_dialog_payload(
            matches, request.user, request.quiniela
        ),
        "tabs": _build_tabs(request.quiniela),
    }
    return render(request, "por_fecha.html", context)


@login_required
@with_quiniela
def team_detail_view(
    request: HttpRequest, team_id: int
) -> HttpResponse:
    """Fragmento HTML de un equipo: bandera HD + todos sus partidos.

    Lo pide ``team_dialog.js`` por fetch al clic en una bandera o un
    nombre de equipo. Mismo decorado de solo lectura que
    ``por_fecha_view`` (día/hora locales, predicción propia,
    ``annotate_result``, ``resolve_sources``) y el mismo dialog de
    partido: el fragmento incrusta su ``build_match_dialog_payload`` para
    que cada tarjeta abra su detalle.
    """
    team = get_object_or_404(Team, pk=team_id)
    matches = list(
        Match.objects.filter(Q(home_team=team) | Q(away_team=team))
        .select_related("home_team", "away_team", "stadium", "stage")
        .order_by("datetime", "of_number")
    )
    preds = {
        p.match_id: p
        for p in Prediction.objects.filter(
            user=request.user, quiniela=request.quiniela,
            match__in=matches,
        ).prefetch_related("rules")
    }
    # Agrupa por fase: las 3 jornadas de grupo se funden en "Fase de
    # grupos"; cada eliminatoria es su propia fase. El queryset viene por
    # fecha, así que las corridas por fase son contiguas.
    phases: list[dict] = []
    current: dict | None = None
    team_points = 0
    team_played = 0
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

        phase_key = "group" if match.is_group else match.stage_id
        if current is None or current["key"] != phase_key:
            current = {
                "key": phase_key,
                "label": ("Fase de grupos" if match.is_group
                          else match.stage.name),
                "matches": [],
                "points": 0,
            }
            phases.append(current)
        current["matches"].append(match)
        if match.is_finished:
            team_played += 1
            if match.user_points is not None:
                current["points"] += match.user_points
                team_points += match.user_points

    # Rival aún sin definir del cruce (ganador real o contendientes); se
    # deja auto-cargar sus fuentes al no ser el set completo de partidos.
    resolve_sources(matches, request.user, request.quiniela)

    # Tabla de posiciones acumulada del grupo (las 6 fechas, no solo los
    # partidos del equipo): el fragmento la muestra bajo la fase de grupos
    # y resalta la fila del equipo.
    group_matches = list(
        Match.objects.filter(
            stage__is_group=True,
            home_team__group_name=team.group_name,
        ).select_related("home_team", "away_team", "stage")
    )
    group_preds = {
        p.match_id: p
        for p in Prediction.objects.filter(
            user=request.user, quiniela=request.quiniela,
            match__in=group_matches,
        )
    }
    standings = build_group_standings(
        group_matches, group_preds
    ).get(team.group_name)

    context = {
        "team": team,
        "phases": phases,
        "team_points": team_points,
        "team_played": team_played,
        "standings": standings,
        "match_dialog_data": build_match_dialog_payload(
            matches, request.user, request.quiniela
        ),
    }
    return render(request, "_team_detail_fragment.html", context)


@login_required
@with_quiniela
def reglas(request: HttpRequest) -> HttpResponse:
    return render(
        request, "reglas.html", {"tabs": _build_tabs(request.quiniela)})