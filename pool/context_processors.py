"""Context processors de la quiniela."""

import logging
from datetime import timedelta

from django.utils import timezone

from pool.models import Prediction, UserQuiniela
from pool.services.leaderboard import build_leaderboard
from pool.services.match_dialog import build_match_dialog_payload
from pool.services.membership import active_quiniela
from tournament.models import Match

logger = logging.getLogger(__name__)

# Ventana en la que el chip del header se muestra "en juego" (barrita de
# carga): hasta 3 h tras el inicio si aún no hay resultado. Más amplia que
# el LIVE_WINDOW de 2 h de las tarjetas, a pedido.
HEADER_LIVE_WINDOW = timedelta(hours=3)

# base-100 de cada tema daisyUI (assets/css/source.css). Alimenta la meta
# theme-color del navegador; default sanginiela si el slug no está mapeado.
THEME_COLORS = {
    "sanginiela": "#0a1c34",
    "medianoche": "#08182b",
    "bienestar": "#2a0f1a",
    "bosque": "#0c1f1a",
    "violeta": "#1a1228",
}
DEFAULT_THEME = "sanginiela"


def quiniela_theme(request) -> dict:
    """Slug del tema y su color base para <html data-theme> y theme-color.

    Corre en todos los templates (login y admin incluidos): resuelve la
    quiniela por path, luego por membresía, y degrada al tema default ante
    cualquier problema; nunca tumba la página.
    """
    slug = DEFAULT_THEME
    try:
        quiniela = getattr(request, "quiniela", None)
        if quiniela is None:
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated:
                quiniela = active_quiniela(user)
        if quiniela is not None:
            slug = quiniela.theme
    except Exception:
        logger.exception("No se pudo resolver el tema de la quiniela")
        slug = DEFAULT_THEME
    if slug not in THEME_COLORS:
        slug = DEFAULT_THEME
    return {
        "quiniela_theme": slug,
        "quiniela_theme_color": THEME_COLORS[slug],
    }


def standing(request) -> dict:
    """Posición del usuario y filas del leaderboard para el header.

    Corre en TODOS los templates (admin y login incluidos): debe
    degradar a {} ante cualquier problema, nunca tumbar la página. El
    dialog de posiciones (header) consume ``board_rows``; el mismo
    ``build_leaderboard`` alimenta el rank-chip, sin query extra.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    try:
        quiniela = getattr(request, "quiniela", None) or active_quiniela(user)
        if quiniela is None:
            return {}
        board = build_leaderboard(quiniela)
        return {
            "my_standing": board.row_for(user),
            "board_max": board.max_points,
            # Quien no ha jugado nada no aparece en la tabla.
            "board_rows": [row for row in board.rows if row.has_played],
        }
    except Exception:
        logger.exception("No se pudo calcular el standing del usuario")
        return {}


def today_matches(request) -> dict:
    """Partidos del día local de la sede para los chips del header.

    "Hoy" se compara contra el día local de cada sede
    (``Match.datetime`` es UTC + ``Stadium.utc_offset``), igual que el
    resto de la app. Cada chip lleva código FIFA + bandera de cada
    selección, marcador estimado (predicción del usuario) y real si el
    partido ya terminó. Degrada a [] ante cualquier problema.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    try:
        quiniela = getattr(request, "quiniela", None) or active_quiniela(user)
        if quiniela is None:
            return {}
        today = timezone.localdate()
        now = timezone.now()
        matches = Match.objects.select_related(
            "home_team", "away_team", "stadium", "stage"
        ).filter(
            datetime__date__gte=today - timedelta(days=1),
            datetime__date__lte=today + timedelta(days=1),
        )
        preds = {
            p.match_id: p
            for p in Prediction.objects.filter(
                user=user, quiniela=quiniela, match__in=matches
            )
        }
        chips = []
        # Objetos crudos que pasan el filtro de "hoy": alimentan el payload
        # del match-dialog para que el chip sea clicleable como las tarjetas.
        today_objs = []
        for match in matches:
            local_dt = match.datetime + timedelta(
                hours=match.stadium.utc_offset
            )
            if local_dt.date() != today:
                continue
            today_objs.append(match)
            pred = preds.get(match.id)
            finished = (
                match.status == "FINISHED"
                and match.home_goals is not None
                and match.away_goals is not None
            )
            chips.append({
                "id": match.id,
                "home": _team_chip(match.home_team, match.home_placeholder),
                "away": _team_chip(match.away_team, match.away_placeholder),
                "pred": (
                    (pred.home_goals, pred.away_goals) if pred else None
                ),
                "real": (
                    (match.home_goals, match.away_goals) if finished else None
                ),
                "is_live": (
                    not finished
                    and match.datetime <= now
                    < match.datetime + HEADER_LIVE_WINDOW
                ),
                "key": match.stage.key,
            })
        return {
            "today_matches": chips,
            "today_dialog_data": build_match_dialog_payload(
                today_objs, user, quiniela
            ),
        }
    except Exception:
        logger.exception("No se pudieron calcular los partidos del día")
        return {}


def quinielas(request) -> dict:
    """Quinielas del usuario y la activa, para el selector del header.

    Corre en todos los templates: degrada a ``{}`` ante cualquier problema.
    ``active_quiniela`` es la resuelta por el path (``request.quiniela``).
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    try:
        memberships = (
            UserQuiniela.objects.filter(user=user)
            .select_related("quiniela")
            .order_by("joined_at")
        )
        return {
            "user_quinielas": [m.quiniela for m in memberships],
            "active_quiniela": getattr(request, "quiniela", None),
        }
    except Exception:
        logger.exception("No se pudieron calcular las quinielas del usuario")
        return {}


def _team_chip(team, placeholder: str) -> dict:
    if team is None:
        return {"code": placeholder, "flag": ""}
    return {"code": team.fifa_code, "flag": team.flag_path}
