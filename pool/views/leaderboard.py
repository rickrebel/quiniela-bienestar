"""Tabla de posiciones del torneo."""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from pool.services.leaderboard import build_leaderboard
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
