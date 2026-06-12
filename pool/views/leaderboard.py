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
        "rows": board.rows,
        "max_points": board.max_points,
        "tabs": _build_tabs(request.user),
    }
    return render(request, "leaderboard.html", context)
