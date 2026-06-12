"""Puntual: sincroniza el resultado real del partido inaugural desde FD.

Correr con:
  python manage.py shell -c "exec(open('.claude/sync_first_result.py',
  encoding='utf-8').read())"
(no por pipe: el shell interactivo no ejecuta el bloque final en EOF).

Si FD trae el marcador, se aplica con apply_fd_result (tarjetas y
raw_fd incluidos). Si FD lo da por terminado pero sin goles todavía
(datos a medio consolidar), se aplica el 2-0 conocido a mano y se
persiste el payload de FD en raw_fd para re-sincronizar después.
"""
import requests
from django.conf import settings

from tournament.models import Match
from tournament.services.fd_results import apply_fd_result, final_goals

KNOWN_SCORE = (2, 0)  # México - Sudáfrica, confirmado por Ricardo


def run() -> None:
    match = Match.objects.select_related("home_team", "away_team").get(
        of_number=1)
    print(f"Partido: {match} · fd_id={match.fd_id} · status={match.status}")

    url = f"{settings.FOOTBALL_DATA_BASE_URL}/matches/{match.fd_id}"
    headers = {"X-Auth-Token": settings.FOOTBALL_DATA_API_TOKEN}
    detail = requests.get(url, headers=headers, timeout=30).json()

    score = detail.get("score") or {}
    fd_status = detail.get("status")
    fd_home = final_goals(score, "home") if score else None
    print(f"FD dice: status={fd_status} · goles local={fd_home}")

    if fd_status == "FINISHED" and fd_home is not None:
        apply_fd_result(match, detail, detail=detail)
        source = "FD completo"
    else:
        match.status = "FINISHED"
        match.home_goals, match.away_goals = KNOWN_SCORE
        match.decided_by = Match.REGULAR
        match.raw_fd = detail
        match.save()
        source = "manual (FD incompleto)"

    match.refresh_from_db()
    print(
        f"Aplicado [{source}]: {match.home_goals}-{match.away_goals} · "
        f"status={match.status} · decided_by={match.decided_by}"
    )


run()
