"""Vistas JSON para guardar y enviar predicciones por fase.

Flujo por ``(user, stage)``:
- ``save`` → borrador (Guardar), mientras la fase sea editable.
- ``send`` → Enviar: persiste, marca ``sent_at``, manda Excel y bloquea
  (envío único y definitivo).
"""

import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from pool.models import Prediction, StageUser, User
from pool.services.excel import generate_excel
from tournament.models import Match

STAGE_NOT_FOUND = "No existe esa fase para tu usuario."
MATCH_NOT_FOUND = "No existe ese partido."
LOCKED = "Esta fase ya no admite cambios."
INCOMPLETE = "Faltan partidos por llenar."


def _get_stage_user(user: User, stage_key: str) -> StageUser | None:
    """StageUser del usuario para la fase, con ``stage`` precargado."""
    return (
        StageUser.objects.select_related("stage")
        .filter(user=user, stage__key=stage_key)
        .first()
    )


def _valid_match_ids(stage_key: str) -> set[int]:
    """IDs de partidos de la fase (acota qué se puede escribir)."""
    return set(
        Match.objects.filter(stage__key=stage_key).values_list(
            "id", flat=True
        )
    )


def _upsert(user: User, preds: list[dict], valid_ids: set[int]) -> None:
    """Crea o actualiza predicciones, ignorando vacíos y ajenos a la fase."""
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
            defaults={
                "home_goals": home,
                "away_goals": away,
                "date": now,
            },
        )


def _saved_match_ids(user: User, stage_key: str) -> set[int]:
    """Partidos de la fase con predicción completa guardada (en BD).

    Una fila ``Prediction`` solo existe si tiene ambos marcadores, así que
    su mera presencia equivale a "partido completo".
    """
    return set(
        Prediction.objects.filter(
            user=user, match__stage__key=stage_key
        ).values_list("match_id", flat=True)
    )


@login_required
@require_POST
def save_predictions(request: HttpRequest) -> JsonResponse:
    """Guarda predicciones de la fase en estado 'saved' (borrador)."""
    data = json.loads(request.body)
    stage_user = _get_stage_user(request.user, data["stage"])
    if stage_user is None:
        return JsonResponse({"error": STAGE_NOT_FOUND}, status=404)
    if not stage_user.can_edit:
        return JsonResponse({"error": LOCKED}, status=403)

    valid_ids = _valid_match_ids(data["stage"])
    with transaction.atomic():
        _upsert(request.user, data["predictions"], valid_ids)
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def save_prediction(
    request: HttpRequest, match_id: int
) -> JsonResponse:
    """Autoguarda un solo partido (al cambiar un marcador).

    Regla del sistema: una fila ``Prediction`` existe solo si el partido
    tiene ambos marcadores. Por eso, si llega completo se hace upsert y, si
    falta cualquiera de los dos, se borra la predicción.
    """
    data = json.loads(request.body)
    match = (
        Match.objects.select_related("stage").filter(id=match_id).first()
    )
    if match is None:
        return JsonResponse({"error": MATCH_NOT_FOUND}, status=404)
    stage_user = (
        StageUser.objects.select_related("stage")
        .filter(user=request.user, stage=match.stage)
        .first()
    )
    if stage_user is None:
        return JsonResponse({"error": STAGE_NOT_FOUND}, status=404)
    if not stage_user.can_edit:
        return JsonResponse({"error": LOCKED}, status=403)

    home = data.get("home_goals")
    away = data.get("away_goals")
    complete = isinstance(home, int) and isinstance(away, int)
    if complete:
        Prediction.objects.update_or_create(
            user=request.user,
            match=match,
            defaults={
                "home_goals": home,
                "away_goals": away,
                "date": timezone.now(),
            },
        )
    else:
        Prediction.objects.filter(user=request.user, match=match).delete()
    return JsonResponse({"status": "ok", "complete": complete})



@login_required
@require_POST
def send_predictions(request: HttpRequest) -> JsonResponse:
    """Envía la fase (estado definitivo): bloquea y manda el Excel.

    La verdad es lo ya guardado en BD por el autoguardado por partido; el
    payload del cliente no se reescribe aquí, solo se usa su ``stage``.
    """
    data = json.loads(request.body)
    stage_user = _get_stage_user(request.user, data["stage"])
    if stage_user is None:
        return JsonResponse({"error": STAGE_NOT_FOUND}, status=404)
    if not stage_user.can_send:
        return JsonResponse({"error": LOCKED}, status=403)

    valid_ids = _valid_match_ids(data["stage"])
    saved_ids = _saved_match_ids(request.user, data["stage"])
    if valid_ids - saved_ids:
        return JsonResponse({"error": INCOMPLETE}, status=400)

    with transaction.atomic():
        stage_user.sent_at = timezone.now()
        stage_user.save(update_fields=["sent_at"])
    generate_excel(request.user, stage_user.stage)
    return JsonResponse({"status": "ok"})
