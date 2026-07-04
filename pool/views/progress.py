"""Vista "Historia": gráfica de la evolución del acumulado por tanda."""

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from pool.models import UserQuiniela
from pool.services.match_dialog import build_match_dialog_payload
from pool.services.progress import MAX_COMPARE, build_progress
from pool.views.scope import with_quiniela


@login_required
@with_quiniela
@ensure_csrf_cookie
def history_view(request: HttpRequest) -> HttpResponse:
    """Página dedicada con la gráfica de líneas de avance. Los datos van
    incrustados (``json_script``). ``ensure_csrf_cookie`` garantiza la
    cookie para el autoguardado de la selección (la página no carga
    ``submit.js``)."""
    data, matches = build_progress(request.quiniela, request.user)
    # Payload del match-dialog de las banderas del eje X: match_dialog.js lo
    # lee de #match-dialog-data al hacer clic en un partido.
    dialog = build_match_dialog_payload(
        matches, request.user, request.quiniela)
    return render(request, "historia.html",
                  {"progress": data, "match_dialog_data": dialog})


@login_required
@with_quiniela
@require_POST
def save_history_compare(request: HttpRequest) -> JsonResponse:
    """Autoguarda (con debounce desde el front) la selección de
    participantes comparados en la gráfica, en su membresía de la
    quiniela activa. Se guardan IDs de usuario en orden de selección;
    ``[]`` es válido (no comparar a nadie)."""
    data = json.loads(request.body)
    ids = [i for i in data.get("ids", []) if isinstance(i, int)][:MAX_COMPARE]
    UserQuiniela.objects.filter(
        user=request.user, quiniela=request.quiniela
    ).update(history_compare=ids)
    return JsonResponse({"status": "ok"})
