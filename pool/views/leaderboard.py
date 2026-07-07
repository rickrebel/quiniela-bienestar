"""Tabla de posiciones del torneo."""

from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import render

from pool.services.leaderboard import (
    build_leaderboard,
    filter_options,
    resolve_filter,
)
from pool.views.scope import with_quiniela
from pool.views.stages import _build_tabs


@login_required
@with_quiniela
def leaderboard_view(request: HttpRequest) -> HttpResponse:
    board = build_leaderboard(request.quiniela)
    context = {
        # Quien no ha jugado nada no aparece en la tabla (pero sigue en
        # board.rows para el context processor `standing`).
        "rows": [r for r in board.rows if r.has_played],
        "max_points": board.max_points,
        "last_position": board.last_position,
        "tabs": _build_tabs(request.quiniela),
    }
    return render(request, "leaderboard.html", context)


@login_required
@with_quiniela
def filtered_board_view(request: HttpRequest) -> HttpResponse:
    """Board acotado a un subconjunto de partidos ("Mini leaderboard").

    Solo GET. ``ambito``/``valor`` definen el corte (ambos vacíos = board
    completo, sin tendencias); ``part=board`` devuelve únicamente la región
    de la tabla (para no destruir el TomSelect al recambiar el filtro). La
    carga inicial trae además las ``options`` de los selects."""
    ambito = request.GET.get("ambito", "").strip()
    valor = request.GET.get("valor", "").strip()
    match_ids: list[int] | None = None
    filtro_label: str | None = None
    if ambito or valor:
        try:
            match_ids, filtro_label = resolve_filter(
                request.quiniela, ambito, valor)
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))

    board = build_leaderboard(
        request.quiniela, match_ids=match_ids, with_trends=False)
    context = {
        "rows": [r for r in board.rows if r.has_played],
        "max_points": board.max_points,
        "last_position": board.last_position,
        "filtro_label": filtro_label,
    }
    if request.GET.get("part") == "board":
        return render(request, "_filtered_board_region.html", context)

    context.update(filter_options(request.quiniela))
    context["ambito"] = ambito
    context["valor"] = valor
    return render(request, "_filtered_board.html", context)
