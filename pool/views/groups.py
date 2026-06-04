"""Vistas de la fase de grupos de la quiniela."""

from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from pool.models import Prediction, User
from pool.utils import convert_date
from tournament.models import Match, Stage


def render_matches_by_group(user: User) -> dict[str, list[Match]]:
    """Agrupa los partidos de la fase de grupos por su grupo.

    Para cada partido adjunta (como atributos en memoria) la fecha
    formateada y, si el usuario ya predijo, los goles predichos. Usa
    select_related en home_team/away_team para evitar consultas N+1, ya
    que el template accede a match.home_team.name y match.away_team.name.
    El grupo se deriva de home_team.group_name (no vive en Match).
    """
    matches = (
        Match.objects.filter(stage__key=Stage.GROUP_STAGE)
        .select_related("home_team", "away_team", "stadium")
    )

    # Indexamos las predicciones del usuario por match_id para hacer
    # el cruce en memoria (una sola consulta).
    predictions = Prediction.objects.filter(user=user)
    predictions_by_match = {p.match_id: p for p in predictions}

    groups: dict[str, list[Match]] = defaultdict(list)
    for match in matches:
        prediction = predictions_by_match.get(match.id)
        if prediction is not None:
            match.predicted_home = prediction.home_goals
            match.predicted_away = prediction.away_goals
        match.formatted_date = convert_date(match.datetime)
        groups[match.home_team.group_name].append(match)

    # dict() obligatorio: en plantillas Django, `groups.items` resuelve
    # primero como acceso por clave (groups["items"]); un defaultdict no
    # lanza KeyError y devuelve [] en lugar de invocar el método .items().
    return dict(groups)


@login_required
def grupos(request: HttpRequest) -> HttpResponse:
    """Renderiza la fase de grupos con las predicciones del usuario.

    'still_submitting' es True mientras el usuario no haya enviado
    (submitted) ninguna predicción de la fase de grupos; controla si
    aún puede editar y enviar sus pronósticos.
    """
    groups = render_matches_by_group(request.user)
    still_submitting = not Prediction.objects.filter(
        user=request.user,
        match__stage__key=Stage.GROUP_STAGE,
        status="submitted",
    ).exists()
    context = {
        "groups": groups,
        "user": request.user,
        "still_submitting": still_submitting,
    }
    return render(request, "grupos.html", context)
