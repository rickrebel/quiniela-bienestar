"""Vistas JSON para guardar, enviar y confirmar predicciones por fase.

Flujo por ``(user, stage)``:
- ``save``   → borrador (Guardar), mientras la fase sea editable.
- ``send``   → Enviar: persiste, marca ``sent_at`` y manda Excel; editable.
- ``confirm``→ Confirmar: marca ``closed_at``, manda Excel final y bloquea.
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


def _missing_ids(preds: list[dict], valid_ids: set[int]) -> set[int]:
    """Partidos de la fase que llegan sin marcador completo."""
    filled = {
        p["match_id"]
        for p in preds
        if p.get("match_id") in valid_ids
        and isinstance(p.get("home_goals"), int)
        and isinstance(p.get("away_goals"), int)
    }
    return valid_ids - filled


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
def send_predictions(request: HttpRequest) -> JsonResponse:
    """Confirma la fase (estado definitivo): bloquea y manda Excel final."""
    data = json.loads(request.body)
    stage_user = _get_stage_user(request.user, data["stage"])
    if stage_user is None:
        return JsonResponse({"error": STAGE_NOT_FOUND}, status=404)
    # if not stage_user.can_confirm:
    #     return JsonResponse({"error": LOCKED}, status=403)

    valid_ids = _valid_match_ids(data["stage"])
    if _missing_ids(data["predictions"], valid_ids):
        return JsonResponse({"error": INCOMPLETE}, status=400)

    with transaction.atomic():
        _upsert(request.user, data["predictions"], valid_ids)
        stage_user.closed_at = timezone.now()
        stage_user.save(update_fields=["closed_at"])
    generate_excel(request.user, stage_user.stage)
    return JsonResponse({"status": "ok"})
