"""Vistas JSON para guardar y enviar predicciones."""

import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from pool.models import Prediction, User
from pool.services.excel import generate_excel

ALREADY_SUBMITTED = (
    "Ya enviaste tus predicciones y no puedes modificarlas"
)


def _process_predictions(
    user: User, preds: list[dict], status: str
) -> dict | None:
    """Crea o actualiza predicciones del usuario.

    Por cada entrada busca la predicción (user, match_id). Si ya
    existe una predicción 'submitted', no permite modificarla y
    devuelve un dict de error (el llamador responde con HTTP 403).
    En caso contrario crea o actualiza con la marca de tiempo actual.
    Devuelve None si todo salió bien.
    """
    now = timezone.now()
    for p in preds:
        prediction = Prediction.objects.filter(
            user=user, match_id=p["match_id"]
        ).first()
        if prediction is not None:
            if prediction.status == "submitted":
                return {"error": ALREADY_SUBMITTED}
            prediction.home_goals = p["goals_a"]
            prediction.away_goals = p["goals_b"]
            prediction.status = status
            prediction.date = now
            prediction.save()
        else:
            Prediction.objects.create(
                date=now,
                user=user,
                match_id=p["match_id"],
                home_goals=p["goals_a"],
                away_goals=p["goals_b"],
                status=status,
            )
    return None


@login_required
@require_POST
def save_predictions(request: HttpRequest) -> JsonResponse:
    """Guarda predicciones en estado 'saved' (borrador).

    Filtra las entradas cuyos goals_a y goals_b sean enteros antes de
    procesarlas, para ignorar campos vacíos del formulario.
    """
    preds = json.loads(request.body)
    filtered = [
        p
        for p in preds
        if isinstance(p.get("goals_a"), int)
        and isinstance(p.get("goals_b"), int)
    ]
    with transaction.atomic():
        error = _process_predictions(request.user, filtered, "saved")
    if error is not None:
        return JsonResponse(error, status=403)
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def submit_predictions(request: HttpRequest) -> JsonResponse:
    """Envía las predicciones (estado 'submitted', definitivo).

    Tras persistir el envío genera el Excel del usuario para que
    refleje exactamente lo enviado.
    """
    data = json.loads(request.body)
    with transaction.atomic():
        error = _process_predictions(
            request.user, data["predictions"], "submitted"
        )
    if error is not None:
        return JsonResponse(error, status=403)
    generate_excel(request.user)
    return JsonResponse({"status": "ok"})
