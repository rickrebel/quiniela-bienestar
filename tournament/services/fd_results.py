"""Mapeo de payloads de football-data.org v4 al modelo ``Match``.

``apply_fd_result`` es la pieza que comparten el sync real durante el
torneo y el comando ``simulate`` (que aplica payloads de la Champions
disfrazados como partidos del Mundial).

Semántica del ``score`` v4, verificada contra PSG-ARS de CL 2025-26
(definido en penales): ``fullTime`` ACUMULA la tanda (5-4 = 1-1 a 120'
+ 4-3 en penales), así que el marcador que puntúa NO puede salir de ahí
en shootouts; se toma de ``regularTime + extraTime``. En partidos
terminados el endpoint de lista ya trae ese desglose — el detail solo
hace falta para ``bookings[]`` (tarjetas), cuando el plan lo incluya.
"""

from tournament.models import Match


def _team_side(entry: dict, home_id: int) -> str:
    return "home" if entry["team"]["id"] == home_id else "away"


def tally_bookings(detail: dict) -> dict[str, int]:
    """Cuenta amarillas/rojas por lado desde ``bookings[]`` del detail."""
    home_id = detail["homeTeam"]["id"]
    counts = {"home_yellow": 0, "away_yellow": 0,
              "home_red": 0, "away_red": 0}
    for booking in detail.get("bookings", []):
        side = _team_side(booking, home_id)
        kind = "yellow" if booking["card"] == "YELLOW" else "red"
        counts[f"{side}_{kind}"] += 1
    return counts


def final_goals(score: dict, side: str) -> int | None:
    """Marcador a 120' (el que puntúa la quiniela) para un lado.

    Con desglose disponible suma regular + extra; sin él (partido
    REGULAR, o payloads viejos) cae a ``fullTime``, que en ese caso sí
    es el marcador real.
    """
    regular = score.get("regularTime")
    if regular is None:
        return score["fullTime"][side]
    extra = score.get("extraTime") or {}
    return regular[side] + (extra.get(side) or 0)


def apply_fd_result(
    match: Match, payload: dict, detail: dict | None = None
) -> Match:
    """Vuelca un payload FD sobre ``match`` y lo guarda.

    ``payload`` es un elemento de ``matches[]`` del endpoint de lista
    (con score desglosado si está FINISHED); ``detail`` (opcional)
    aporta tarjetas vía ``bookings[]``. Se persiste en ``raw_fd`` el
    payload más rico disponible.
    """
    score = payload["score"]
    match.status = payload["status"]
    match.home_goals = final_goals(score, "home")
    match.away_goals = final_goals(score, "away")
    match.decided_by = score.get("duration") or ""

    shootout = score.get("penalties")
    if match.decided_by == Match.PENALTY_SHOOTOUT and shootout:
        match.home_penalties = shootout["home"]
        match.away_penalties = shootout["away"]

    if detail is not None:
        cards = tally_bookings(detail)
        match.home_yellow = cards["home_yellow"]
        match.away_yellow = cards["away_yellow"]
        match.home_red = cards["home_red"]
        match.away_red = cards["away_red"]

    match.raw_fd = detail if detail is not None else payload
    match.save()
    return match
