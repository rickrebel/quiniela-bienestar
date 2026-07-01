"""Resolución del cruce de eliminatoria: ganador real o contendientes.

Los partidos de octavos en adelante guardan su origen como placeholder
textual: ``"W74"`` (ganador del partido nº 74) o ``"L101"`` (perdedor del
101, solo el 3.er lugar). El FK ``home_team``/``away_team`` queda nulo
hasta conocerse el cruce. Aquí se resuelve **en memoria y solo desde la
BD**: si el partido origen ya terminó se rellena el equipo que avanza (o
el que cae); si no, y el origen tiene sus dos equipos en BD, se exponen
los dos contendientes para que la tarjeta los muestre con bandera + CODE,
realzando al que el jugador estimó que pasaría.
"""

import re
from dataclasses import dataclass

from django.db.models import Q

from pool.models import Prediction, Quiniela, User
from tournament.models import Match, Team

# "W74" = ganador del partido 74; "L101" = perdedor del 101 (3.er lugar).
SOURCE_RE = re.compile(r"^([WL])(\d+)$")


@dataclass
class Contender:
    """Un equipo candidato a ocupar un slot, con su realce de pronóstico."""

    team: Team
    picked: bool


def winner_team(match: Match) -> Team | None:
    """Equipo que avanzó de un partido de eliminatoria terminado.

    Compara goles de 90'/prórroga; si el marcador empató y se resolvió por
    penales, gana quien convirtió más. ``None`` si el partido no ha
    terminado o le faltan equipos (misma jerarquía que ``annotate_result``
    usa para el subrayado, extraída para reutilizarla aquí)."""
    if match.status != "FINISHED" or match.home_goals is None:
        return None
    if match.home_team_id is None or match.away_team_id is None:
        return None
    if match.home_goals > match.away_goals:
        return match.home_team
    if match.away_goals > match.home_goals:
        return match.away_team
    if match.decided_by == Match.PENALTY_SHOOTOUT:
        return (
            match.home_team
            if (match.home_penalties or 0) > (match.away_penalties or 0)
            else match.away_team
        )
    return None


def loser_team(match: Match) -> Team | None:
    """El otro equipo del ganador (para el cruce del 3.er lugar)."""
    winner = winner_team(match)
    if winner is None:
        return None
    return (
        match.away_team if winner.id == match.home_team_id
        else match.home_team
    )


def _predicted_winner_id(
    source: Match, pred: Prediction | None
) -> int | None:
    """Equipo que el jugador pronosticó ganador del partido origen.

    Si su marcador no es empate, el de más goles; si empató, su pick de
    penales (``advancing_team``, que puede ser ``None``)."""
    if pred is None or pred.home_goals is None:
        return None
    if pred.home_goals > pred.away_goals:
        return source.home_team_id
    if pred.away_goals > pred.home_goals:
        return source.away_team_id
    return pred.advancing_team_id


def _resolve_slot(
    placeholder: str,
    source_by_number: dict[int, Match],
    preds_by_match: dict[int, Prediction],
) -> tuple[Team | None, list[Contender] | None]:
    """Resuelve un slot ``W##``/``L##``.

    Devuelve ``(equipo, None)`` si el origen ya tiene ganador, ``(None,
    contendientes)`` si aún no pero el origen tiene ambos equipos en BD, o
    ``(None, None)`` si no hay nada que mostrar (placeholder de grupo,
    origen ausente o sin equipos)."""
    matched = SOURCE_RE.match(placeholder or "")
    if not matched:
        return None, None
    kind, number = matched.group(1), int(matched.group(2))
    source = source_by_number.get(number)
    if source is None:
        return None, None

    resolved = winner_team(source) if kind == "W" else loser_team(source)
    if resolved is not None:
        return resolved, None

    if source.home_team_id is None or source.away_team_id is None:
        return None, None

    pred = preds_by_match.get(source.id)
    won_id = _predicted_winner_id(source, pred)
    # Para el 3.er lugar ("L##") se realza al que el jugador estimó que
    # caería: el contendiente que NO es su ganador pronosticado.
    if kind == "W":
        picked_id = won_id
    elif won_id is None:
        picked_id = None
    else:
        picked_id = (
            source.away_team_id if won_id == source.home_team_id
            else source.home_team_id
        )
    return None, [
        Contender(source.home_team, source.home_team_id == picked_id),
        Contender(source.away_team, source.away_team_id == picked_id),
    ]


def resolve_sources(
    targets: list[Match],
    user: User,
    quiniela: Quiniela,
    source_by_number: dict[int, Match] | None = None,
    preds_by_match: dict[int, Prediction] | None = None,
) -> None:
    """Rellena en memoria ganador/contendientes de los slots ``W##``/``L##``.

    Por cada partido en ``targets`` fija ``home_team``/``away_team`` (si el
    origen ya tiene ganador y el slot estaba vacío) o
    ``home_contenders``/``away_contenders`` (lista de ``Contender``). Solo
    usa equipos presentes en BD. ``source_by_number``/``preds_by_match``
    permiten reutilizar datos ya cargados (vista por-fecha) y evitar
    queries; si faltan, se consultan a partir de los placeholders."""
    numbers = set()
    for match in targets:
        for placeholder in (match.home_placeholder, match.away_placeholder):
            matched = SOURCE_RE.match(placeholder or "")
            if matched:
                numbers.add(int(matched.group(2)))
    if not numbers:
        return

    if source_by_number is None:
        source_by_number = {
            s.of_number: s
            for s in Match.objects.filter(
                of_number__in=numbers
            ).select_related("home_team", "away_team")
        }
    if preds_by_match is None:
        source_ids = [s.id for s in source_by_number.values()]
        preds_by_match = {
            p.match_id: p
            for p in Prediction.objects.filter(
                user=user, quiniela=quiniela, match_id__in=source_ids
            )
        }

    for match in targets:
        for side in ("home", "away"):
            placeholder = getattr(match, f"{side}_placeholder")
            team, contenders = _resolve_slot(
                placeholder, source_by_number, preds_by_match
            )
            if team is not None and getattr(match, f"{side}_team") is None:
                setattr(match, f"{side}_team", team)
            elif contenders is not None:
                setattr(match, f"{side}_contenders", contenders)


def propagate_result(match: Match) -> list[Match]:
    """Escribe en BD el equipo que avanza/cae en la fase siguiente.

    Al capturar el resultado de un partido de eliminatoria, rellena el FK
    ``home_team``/``away_team`` de los partidos cuya ranura apunta a este
    (``"W74"`` → ganador, ``"L74"`` → perdedor). Así el cruce se va
    materializando solo, partido a partido. No-op si el partido aún no
    tiene ganador (grupos, sin equipos o empate sin penales). Idempotente:
    solo escribe cuando el FK cambia. Devuelve los partidos modificados."""
    winner = winner_team(match)
    if winner is None:
        return []
    team_by_kind = {"W": winner, "L": loser_team(match)}
    refs = [f"W{match.of_number}", f"L{match.of_number}"]
    targets = Match.objects.filter(
        Q(home_placeholder__in=refs) | Q(away_placeholder__in=refs)
    )
    updated = []
    for target in targets:
        fields = []
        for side in ("home", "away"):
            matched = SOURCE_RE.match(getattr(target, f"{side}_placeholder"))
            if not matched or int(matched.group(2)) != match.of_number:
                continue
            team = team_by_kind[matched.group(1)]
            if team is not None and getattr(target, f"{side}_team_id") != team.id:
                setattr(target, f"{side}_team", team)
                fields.append(f"{side}_team")
        if fields:
            target.save(update_fields=fields)
            updated.append(target)
    return updated
