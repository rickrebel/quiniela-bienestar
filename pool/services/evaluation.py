"""Congela los puntos de cada pronóstico y el acumulado por partido.

Antes el scoring se calculaba al vuelo en cada carga de página; ahora se
persiste para no recalcular, integrar ambas quinielas y graficar el
avance. ``recompute_all`` es la única función autoritativa: idempotente y
completa (resetea y reevalúa todo), se llama tras cada captura de
resultado.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from pool.models import (
    Prediction, Quiniela, ScoreSnapshot, User, UserQuiniela)
from pool.services.scoring import ScoreDetail, score_detail
from tournament.models import Match

ZERO = Decimal("0")


def rule_maps(quiniela: Quiniela) -> tuple[dict[str, int], dict[str, "Rule"]]:
    """``{code: points}`` y ``{code: Rule}`` de una quiniela concreta."""
    points_by_code = {}
    rules_by_code = {}
    for qr in quiniela.quiniela_rules.all():
        points_by_code[qr.rule.code] = qr.points
        rules_by_code[qr.rule.code] = qr.rule
    return points_by_code, rules_by_code


def multiplier_resolver(
    quiniela: Quiniela,
) -> Callable[[Match], Decimal]:
    """Fábrica del resolvedor de multiplicador por partido.

    El peso normal es el de la ventana que cubre la fase del partido, salvo
    el tercer lugar cuando la ventana define ``third_place_multiplier`` (los
    dos partidos de la final comparten ``Stage``/``Window``, pero se quiere
    ponderar el tercer lugar aparte). Precalcula los dicts en una sola
    pasada sobre las ventanas (con ``stages`` prefetcheadas) y devuelve una
    función barata por partido.
    """
    by_stage: dict[int, Decimal] = {}
    third_by_stage: dict[int, Decimal] = {}
    for window in quiniela.windows.all():
        for stage in window.stages.all():
            by_stage[stage.id] = window.multiplier
            if window.third_place_multiplier is not None:
                third_by_stage[stage.id] = window.third_place_multiplier

    def resolve(match: Match) -> Decimal:
        if match.is_third_place and match.stage_id in third_by_stage:
            return third_by_stage[match.stage_id]
        return by_stage.get(match.stage_id, Decimal("1"))

    return resolve


def _hit_codes(
    detail: ScoreDetail, is_draw: bool, penalty_hit: bool = False
) -> list[str]:
    """Códigos de regla que el pronóstico atinó (escalones aditivos).

    DIFF se enciende también con un exacto no-empate: el exacto incluye
    la diferencia, así RESULT+DIFF+EXACT suman 5 sin doble-contar. PENALTY
    es independiente del marcador: lo decide ``advancing_team`` (el
    contexto de penales ya llega resuelto en ``penalty_hit``).
    """
    codes = []
    if detail.outcome:
        codes.append("RESULT")
    if detail.diff_bonus or (detail.exact and not is_draw):
        codes.append("DIFF")
    if detail.exact:
        codes.append("EXACT")
    if penalty_hit:
        codes.append("PENALTY")
    return codes


@dataclass(frozen=True)
class ScorelineEval:
    """Resultado de evaluar un marcador contra el real."""

    points: Decimal      # base ya × Window.multiplier
    base: int            # suma de reglas atinadas, sin ponderar
    codes: list[str]     # códigos de reglas atinadas


def _penalty_winner_id(match: Match) -> int | None:
    """Equipo que ganó la tanda de penales (más penales convertidos)."""
    return (
        match.home_team_id
        if (match.home_penalties or 0) > (match.away_penalties or 0)
        else match.away_team_id
    )


def evaluate_scoreline(
    pred_home: int, pred_away: int, match: Match,
    points_by_code: dict[str, int],
    advancing_team_id: int | None = None,
    multiplier: Decimal = Decimal("1"),
) -> ScorelineEval | None:
    """Puntos y reglas de un marcador contra el resultado real de
    ``match``. Único punto de cálculo: lo reusan ``recompute_all`` y el
    dialog (marcadores hipotéticos). ``None`` si aún no hay resultado.

    ``advancing_team_id`` solo importa en knockouts decididos por penales
    con empate pronosticado: si coincide con el ganador real de la tanda y
    la quiniela puntúa PENALTY, suma ese escalón. Las llamadas que no lo
    pasan (marcadores hipotéticos) nunca lo activan.

    ``multiplier`` es el ponderador de la ventana (``Window``) que cubre la
    fase del partido en esa quiniela; lo resuelve el llamador (default 1).
    """
    detail = score_detail(
        pred_home, pred_away, match.home_goals, match.away_goals)
    if detail is None:
        return None
    is_draw = match.home_goals == match.away_goals
    penalty_hit = (
        "PENALTY" in points_by_code
        and not match.stage.is_group
        and match.decided_by == Match.PENALTY_SHOOTOUT
        and pred_home == pred_away
        and advancing_team_id is not None
        and advancing_team_id == _penalty_winner_id(match)
    )
    codes = [
        c for c in _hit_codes(detail, is_draw, penalty_hit)
        if c in points_by_code
    ]
    base = sum(points_by_code[c] for c in codes)
    return ScorelineEval(
        points=Decimal(base) * multiplier,
        base=base, codes=codes,
    )


@transaction.atomic
def recompute_all() -> None:
    """Reevalúa todos los pronósticos y reconstruye los snapshots.

    Recorre cada quiniela por separado: sus reglas (``QuinielaRule``) y el
    peso por fase (desde sus ``Window``) son independientes, así que el
    mismo marcador puede valer distinto en cada una. El reset (M2M de
    reglas y campos congelados) es global y va antes del recorrido.
    """
    through = Prediction.rules.through
    through.objects.all().delete()
    Prediction.objects.update(
        base_points=None, points=None, evaluated_at=None)

    finished = list(
        Match.objects.filter(
            status="FINISHED",
            home_goals__isnull=False,
            away_goals__isnull=False,
        ).select_related("stage")
    )
    finished_by_id = {m.id: m for m in finished}
    now = timezone.now()

    quinielas = Quiniela.objects.prefetch_related(
        "quiniela_rules__rule", "windows__stages")
    for quiniela in quinielas:
        points_by_code, rules_by_code = rule_maps(quiniela)
        resolve_multiplier = multiplier_resolver(quiniela)
        to_update = []
        through_rows = []
        predictions = Prediction.objects.filter(
            quiniela=quiniela, match_id__in=finished_by_id)
        for pred in predictions:
            match = finished_by_id[pred.match_id]
            evaluation = evaluate_scoreline(
                pred.home_goals, pred.away_goals, match, points_by_code,
                advancing_team_id=pred.advancing_team_id,
                multiplier=resolve_multiplier(match))
            if evaluation is None:
                continue
            pred.base_points = evaluation.base
            pred.points = evaluation.points
            pred.evaluated_at = now
            to_update.append(pred)
            through_rows.extend(
                through(prediction_id=pred.id, rule_id=rules_by_code[c].id)
                for c in evaluation.codes
            )

        Prediction.objects.bulk_update(
            to_update, ["base_points", "points", "evaluated_at"])
        through.objects.bulk_create(through_rows)
        rebuild_snapshots(quiniela, finished)


def _dense_positions(
    cumulative: dict[int, Decimal], ranked_ids: list[int]
) -> dict[int, int]:
    """Ranking denso (1-2-2-3) por puntos acumulados; empates comparten
    lugar. Solo ordena a ``ranked_ids`` (excluye el perfil virtual)."""
    positions = {}
    previous_points = None
    position = 0
    for uid in sorted(ranked_ids, key=lambda u: -cumulative[u]):
        if previous_points is None or cumulative[uid] != previous_points:
            position += 1
        positions[uid] = position
        previous_points = cumulative[uid]
    return positions


def rebuild_snapshots(
    quiniela: Quiniela, finished: list[Match] | None = None
) -> None:
    """Recalcula el acumulado por (usuario × partido) de una quiniela.

    El tick es el conjunto de partidos con el mismo ``datetime``: se
    suma todo el tick antes de fijar acumulado y posición, así los
    partidos simultáneos comparten el mismo valor. El perfil virtual
    acumula y aparece, pero queda fuera del ranking (``position`` nula).
    Solo participan los miembros de la quiniela (``UserQuiniela``); el
    acumulado y la posición son independientes por quiniela.
    """
    if finished is None:
        finished = list(
            Match.objects.filter(
                status="FINISHED",
                home_goals__isnull=False,
                away_goals__isnull=False,
            )
        )
    finished.sort(key=lambda m: (m.datetime, m.of_number))

    member_ids = UserQuiniela.objects.filter(
        quiniela=quiniela).values_list("user_id", flat=True)
    users = list(
        User.objects.filter(id__in=member_ids).filter(
            Q(is_active=True) | Q(is_virtual=True))
    )
    ranked_ids = [u.id for u in users if not u.is_virtual]

    pred_points = {
        (uid, mid): pts
        for uid, mid, pts in Prediction.objects.filter(
            quiniela=quiniela,
            match_id__in=[m.id for m in finished], points__isnull=False
        ).values_list("user_id", "match_id", "points")
    }

    cumulative = {u.id: ZERO for u in users}
    ScoreSnapshot.objects.filter(quiniela=quiniela).delete()
    rows = []
    for _, tick in groupby(finished, key=lambda m: m.datetime):
        tick_matches = list(tick)
        for match in tick_matches:
            for uid in cumulative:
                cumulative[uid] += pred_points.get((uid, match.id), ZERO)
        positions = _dense_positions(cumulative, ranked_ids)
        for match in tick_matches:
            for user in users:
                rows.append(ScoreSnapshot(
                    quiniela_id=quiniela.id,
                    user_id=user.id,
                    match_id=match.id,
                    cumulative_points=cumulative[user.id],
                    position=positions.get(user.id),
                ))
    ScoreSnapshot.objects.bulk_create(rows)