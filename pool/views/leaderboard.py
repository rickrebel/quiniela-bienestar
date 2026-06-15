"""Tabla de posiciones del torneo."""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from pool.services.leaderboard import build_leaderboard
from pool.views.stages import _build_tabs


@login_required
def leaderboard_view(request: HttpRequest) -> HttpResponse:
    board = build_leaderboard()
    context = {
        # Quien no ha jugado nada no aparece en la tabla (pero sigue en
        # board.rows para el context processor `standing`).
        "rows": [row for row in board.rows if row.has_played],
        "max_points": board.max_points,
        "tabs": _build_tabs(request.user),
    }
    return render(request, "leaderboard.html", context)
