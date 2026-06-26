"""Vista "Historia": gráfica de la evolución del acumulado por tanda."""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from pool.services.progress import build_progress
from pool.views.scope import with_quiniela


@login_required
@with_quiniela
def history_view(request: HttpRequest) -> HttpResponse:
    """Página dedicada con la gráfica de líneas de avance. Los datos van
    incrustados (``json_script``); no hay endpoint aparte."""
    data = build_progress(request.quiniela, request.user)
    return render(request, "historia.html", {"progress": data})
