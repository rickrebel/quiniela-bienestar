"""Captura manual del resultado oficial de un partido.

La API de FD no llega a tiempo, así que usuarios de confianza
(``User.can_record_results``) o superusers capturan goles, tarjetas y
penales desde el dialog de detalle. El sync de FD posterior puede
sobrescribir/corregir lo capturado (p. ej. ``decided_by``).
"""

import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from tournament.models import Match, Stage

FORBIDDEN = "No tienes permiso para capturar resultados."
MATCH_NOT_FOUND = "No existe ese partido."
TOO_EARLY = "El partido aún no termina; espera al final."
ALREADY_FINISHED = "Este resultado ya fue capturado y no se puede cambiar."
INVALID_NUMBER = "Todos los campos deben ser números enteros (0 o más)."
PENALTIES_NOT_ALLOWED = "Solo hay penales en eliminatorias con empate."
PENALTIES_REQUIRED = "Con empate en eliminatorias faltan los penales."
PENALTIES_TIED = "Los penales no pueden quedar empatados."

# 90' + descanso + agregado: a los 105' del inicio ya hay resultado
# confiable que capturar. Espejo en match_dialog.js (RECORD_DELAY_MS).
RECORD_DELAY = timedelta(minutes=105)

REQUIRED_FIELDS = (
    "home_goals", "away_goals",
    "home_yellow", "away_yellow",
    "home_red", "away_red",
)


def _as_score(value) -> int | None:
    """Entero >= 0 o None; bool y strings se rechazan (json.loads puede
    traer True o "2" y un Positive*Field los aceptaría en silencio)."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


@login_required
@require_POST
def record_result(request: HttpRequest, match_id: int) -> JsonResponse:
    """Captura goles, tarjetas y penales; deja el partido FINISHED.

    Inmutable: una vez terminado (capturado o sincronizado de FD) el
    servidor rechaza recapturas aunque la UI muestre la opción.
    """
    user = request.user
    if not (user.can_record_results or user.is_superuser):
        return JsonResponse({"error": FORBIDDEN}, status=403)
    match = (
        Match.objects.select_related("stage").filter(id=match_id).first()
    )
    if match is None:
        return JsonResponse({"error": MATCH_NOT_FOUND}, status=404)
    if timezone.now() < match.datetime + RECORD_DELAY:
        return JsonResponse({"error": TOO_EARLY}, status=403)
    finished = (
        match.status == "FINISHED"
        and match.home_goals is not None
        and match.away_goals is not None
    )
    if finished:
        return JsonResponse({"error": ALREADY_FINISHED}, status=409)

    data = json.loads(request.body)
    values = {f: _as_score(data.get(f)) for f in REQUIRED_FIELDS}
    if any(v is None for v in values.values()):
        return JsonResponse({"error": INVALID_NUMBER}, status=400)
    pens_raw = (data.get("home_penalties"), data.get("away_penalties"))
    has_pens = any(p is not None for p in pens_raw)
    home_pens, away_pens = (_as_score(p) for p in pens_raw)
    if has_pens and (home_pens is None or away_pens is None):
        return JsonResponse({"error": INVALID_NUMBER}, status=400)

    tied = values["home_goals"] == values["away_goals"]
    is_knockout = match.stage.key != Stage.GROUP_STAGE
    if has_pens and not (tied and is_knockout):
        return JsonResponse({"error": PENALTIES_NOT_ALLOWED}, status=400)
    if tied and is_knockout and not has_pens:
        return JsonResponse({"error": PENALTIES_REQUIRED}, status=400)
    if has_pens and home_pens == away_pens:
        return JsonResponse({"error": PENALTIES_TIED}, status=400)

    for field, value in values.items():
        setattr(match, field, value)
    match.status = "FINISHED"
    # Sin penales no se distingue REGULAR de EXTRA_TIME; el sync de FD
    # lo corrige después y para el scoring es irrelevante.
    if has_pens:
        match.decided_by = Match.PENALTY_SHOOTOUT
        match.home_penalties = home_pens
        match.away_penalties = away_pens
    else:
        match.decided_by = Match.REGULAR
    match.save(update_fields=[
        *REQUIRED_FIELDS, "status", "decided_by",
        "home_penalties", "away_penalties",
    ])
    return JsonResponse({"status": "ok"})
