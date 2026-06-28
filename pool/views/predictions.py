"""Vistas JSON para guardar y enviar predicciones por ventana.

Flujo por ``(user, quiniela, window)``:
- ``save`` → borrador (Guardar), mientras la ventana sea editable.
- ``send`` → Enviar: persiste, marca ``sent_at``, manda Excel y bloquea
  (envío único y definitivo). La quiniela activa la fija el path
  (``request.quiniela``); la ventana, su ``order`` en el payload.
"""

import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from pool.models import Prediction, Quiniela, User, Window, WindowUser
from pool.services.excel import generate_excel
from pool.views.scope import with_quiniela
from tournament.models import Match, Stage

WINDOW_NOT_FOUND = "No existe esa ventana para tu usuario."
MATCH_NOT_FOUND = "No existe ese partido."
LOCKED = "Esta ventana ya no admite cambios."
MATCH_STARTED = "Ese partido ya comenzó; no admite cambios."
INCOMPLETE = "Faltan partidos por llenar."


def _get_window_user(
    user: User, quiniela: Quiniela, order: int
) -> WindowUser | None:
    """WindowUser del usuario para la ventana (por su ``order``)."""
    return (
        WindowUser.objects.select_related("window")
        .filter(user=user, window__quiniela=quiniela, window__order=order)
        .first()
    )


def _window_for_stage(quiniela: Quiniela, stage: Stage) -> Window | None:
    """Ventana de la quiniela que cubre esa fase (autosave por partido)."""
    return Window.objects.filter(quiniela=quiniela, stages=stage).first()


def _editable_match_ids(window: Window) -> set[int]:
    """Partidos de la ventana cuyo kickoff aún no llega (editables).

    Candado por partido: aunque la ventana siga abierta, un partido ya
    iniciado deja de admitir cambios. ``datetime`` está en UTC.
    """
    return set(
        Match.objects.filter(
            stage__in=window.stages.all(),
            datetime__gt=timezone.now(),
        ).values_list("id", flat=True)
    )


def _upsert(
    user: User, quiniela: Quiniela, preds: list[dict], valid_ids: set[int]
) -> None:
    """Crea/actualiza predicciones de la quiniela, ignorando vacíos y
    ajenas a la ventana."""
    now = timezone.now()
    for p in preds:
        match_id = p.get("match_id")
        home = p.get("home_goals")
        away = p.get("away_goals")
        if match_id not in valid_ids:
            continue
        if not isinstance(home, int) or not isinstance(away, int):
            continue
        Prediction.objects.update_or_create(
            user=user,
            match_id=match_id,
            quiniela=quiniela,
            defaults={
                "home_goals": home,
                "away_goals": away,
                "date": now,
            },
        )


def _saved_match_ids(
    user: User, quiniela: Quiniela, window: Window
) -> set[int]:
    """Partidos de la ventana con predicción completa guardada (en BD).

    Una fila ``Prediction`` solo existe si tiene ambos marcadores, así que
    su mera presencia equivale a "partido completo".
    """
    return set(
        Prediction.objects.filter(
            user=user, quiniela=quiniela,
            match__stage__in=window.stages.all(),
        ).values_list("match_id", flat=True)
    )


@login_required
@with_quiniela
@require_POST
def save_predictions(request: HttpRequest) -> JsonResponse:
    """Guarda predicciones de la ventana en estado 'saved' (borrador)."""
    data = json.loads(request.body)
    window_user = _get_window_user(
        request.user, request.quiniela, data["window"])
    if window_user is None:
        return JsonResponse({"error": WINDOW_NOT_FOUND}, status=404)
    if not window_user.can_edit:
        return JsonResponse({"error": LOCKED}, status=403)

    # Solo partidos no iniciados son escribibles (candado por partido).
    valid_ids = _editable_match_ids(window_user.window)
    with transaction.atomic():
        _upsert(
            request.user, request.quiniela, data["predictions"], valid_ids)
    return JsonResponse({"status": "ok"})


@login_required
@with_quiniela
@require_POST
def save_prediction(
    request: HttpRequest, match_id: int
) -> JsonResponse:
    """Autoguarda un solo partido de la quiniela activa (al cambiar un
    marcador).

    Regla del sistema: una fila ``Prediction`` existe solo si el partido
    tiene ambos marcadores. Por eso, si llega completo se hace upsert y, si
    falta cualquiera de los dos, se borra la predicción.
    """
    data = json.loads(request.body)
    quiniela = request.quiniela
    match = (
        Match.objects.select_related("stage").filter(id=match_id).first()
    )
    if match is None:
        return JsonResponse({"error": MATCH_NOT_FOUND}, status=404)
    window = _window_for_stage(quiniela, match.stage)
    if window is None:
        return JsonResponse({"error": WINDOW_NOT_FOUND}, status=404)
    window_user = (
        WindowUser.objects.filter(user=request.user, window=window).first()
    )
    if window_user is None:
        return JsonResponse({"error": WINDOW_NOT_FOUND}, status=404)
    if not window_user.can_edit:
        return JsonResponse({"error": LOCKED}, status=403)
    if match.has_started:
        return JsonResponse({"error": MATCH_STARTED}, status=403)

    home = data.get("home_goals")
    away = data.get("away_goals")
    complete = isinstance(home, int) and isinstance(away, int)
    if complete:
        # advancing_team solo aplica a un empate pronosticado en
        # eliminatoria; en cualquier otro caso se limpia (None).
        advancing_id = data.get("advancing_team_id")
        valid_advancing = (
            not match.stage.is_group
            and home == away
            and advancing_id in (match.home_team_id, match.away_team_id)
        )
        Prediction.objects.update_or_create(
            user=request.user,
            match=match,
            quiniela=quiniela,
            defaults={
                "home_goals": home,
                "away_goals": away,
                "date": timezone.now(),
                "advancing_team_id": advancing_id if valid_advancing else None,
            },
        )
    else:
        Prediction.objects.filter(
            user=request.user, match=match, quiniela=quiniela).delete()
    return JsonResponse({"status": "ok", "complete": complete})


@login_required
@with_quiniela
@require_POST
def send_predictions(request: HttpRequest) -> JsonResponse:
    """Envía la ventana (estado definitivo): bloquea y manda el Excel.

    La verdad es lo ya guardado en BD por el autoguardado por partido; el
    payload del cliente no se reescribe aquí, solo se usa su ``window``.
    """
    data = json.loads(request.body)
    window_user = _get_window_user(
        request.user, request.quiniela, data["window"])
    if window_user is None:
        return JsonResponse({"error": WINDOW_NOT_FOUND}, status=404)
    if not window_user.can_send:
        return JsonResponse({"error": LOCKED}, status=403)

    window = window_user.window
    # La completitud solo exige los partidos no iniciados: uno ya comenzado
    # y sin llenar no bloquea el envío (cuenta 0).
    required_ids = _editable_match_ids(window)
    saved_ids = _saved_match_ids(request.user, request.quiniela, window)
    if required_ids - saved_ids:
        return JsonResponse({"error": INCOMPLETE}, status=400)

    with transaction.atomic():
        window_user.sent_at = timezone.now()
        window_user.save(update_fields=["sent_at"])
    generate_excel(request.user, window, request.quiniela)
    return JsonResponse({"status": "ok"})
