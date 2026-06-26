"""Cálculo de puntos de un pronóstico contra el resultado real.

Reglas (ver ``templates/reglas.html``, documentadas para los jugadores):

- Atinar al resultado del partido (ganador o empate): 3 puntos.
- Atinar también la diferencia de goles: +1 punto. Solo aplica si se
  atinó al resultado, y nunca en empates.
- Marcador exacto: +1 punto más (5 totales con ganador, 4 en empate).

En eliminatorias se compara el marcador en tiempo regular/extra
(``Match.home_goals``/``away_goals``), nunca los penales.
"""

from dataclasses import dataclass

HOME_WINS = "home"
AWAY_WINS = "away"
DRAW = "draw"


@dataclass(frozen=True)
class ScoreDetail:
    """Puntos con desglose. ``exact`` y ``diff_bonus`` son disjuntos:
    un 4 puede ser exacto-empate o ganador+diferencia, así que los
    conteos deben salir de estos flags, nunca del valor numérico.
    ``outcome`` no es disjunto: marca todo acierto de resultado
    (exacto y diferencia lo implican).
    """

    points: int
    outcome: bool
    exact: bool
    diff_bonus: bool


def _match_result(home_goals: int, away_goals: int) -> str:
    """Resultado del partido: gana local, gana visitante o empate."""
    if home_goals > away_goals:
        return HOME_WINS
    if home_goals < away_goals:
        return AWAY_WINS
    return DRAW


def score_detail(
    pred_home: int | None,
    pred_away: int | None,
    actual_home: int | None,
    actual_away: int | None,
) -> ScoreDetail | None:
    """Evalúa un pronóstico contra el marcador real.

    Devuelve ``None`` si falta algún dato: "sin resultado" no es lo
    mismo que "cero puntos".
    """
    if None in (pred_home, pred_away, actual_home, actual_away):
        return None

    predicted_result = _match_result(pred_home, pred_away)
    actual_result = _match_result(actual_home, actual_away)

    if predicted_result != actual_result:
        return ScoreDetail(points=0, outcome=False, exact=False, diff_bonus=False)

    is_draw = actual_result == DRAW
    exact_score = (pred_home, pred_away) == (actual_home, actual_away)
    if exact_score:
        # El exacto ya incluye la diferencia: 3 + 1 + 1 (o 3 + 1 en empate).
        points = 4 if is_draw else 5
        return ScoreDetail(points=points, outcome=True, exact=True, diff_bonus=False)

    same_difference = (pred_home - pred_away) == (actual_home - actual_away)
    diff_bonus = same_difference and not is_draw
    points = 4 if diff_bonus else 3
    return ScoreDetail(points=points, outcome=True, exact=False, diff_bonus=diff_bonus)


def calculate_points(
    pred_home: int | None,
    pred_away: int | None,
    actual_home: int | None,
    actual_away: int | None,
) -> int | None:
    detail = score_detail(pred_home, pred_away, actual_home, actual_away)
    return detail.points if detail else None


def chips_from_codes(
    codes, is_draw: bool, show_penalty: bool = False
) -> list[dict]:
    """Chips de desglose a partir de los códigos de regla atinados.

    Lee lo guardado (``Prediction.rules``) en vez del ``ScoreDetail``
    calculado al vuelo. La diferencia nunca cuenta en empates, así que en
    empate **se omite** el chip "Dif" (no se pinta como ``na``). En
    knockouts decididos por penales (``show_penalty``) se añade el chip
    "Pen" con el acierto del equipo que avanza.
    """
    has = set(codes)
    chips = [
        {"label": "Res", "icon": "check",
         "state": "on" if "RESULT" in has else "off"},
    ]
    if not is_draw:
        chips.append(
            {"label": "Dif", "icon": "",
             "state": "on" if "DIFF" in has else "off"})
    chips.append(
        {"label": "", "icon": "mira",
         "state": "on" if "EXACT" in has else "off"})
    if show_penalty:
        chips.append(
            {"label": "Pen", "icon": "",
             "state": "on" if "PENALTY" in has else "off"})
    return chips


def result_chips(detail: ScoreDetail, is_draw: bool) -> list[dict]:
    """Tres chips de desglose (Resultado, Diferencia, Exacto).

    ``state`` alimenta el color: ``on`` (punto ganado), ``off`` (no) o
    ``na`` (no aplica: la diferencia nunca cuenta en empates). El exacto
    incluye la diferencia, por eso enciende también su chip salvo empate.
    Lo consumen la tarjeta (``<c-chip>``) y el dialog (lo pinta en JS).
    """
    diff_on = detail.diff_bonus or (detail.exact and not is_draw)
    return [
        {"label": "Res", "icon": "check",
         "state": "on" if detail.points else "off"},
        {"label": "Dif", "icon": "",
         "state": "na" if is_draw else ("on" if diff_on else "off")},
        {"label": "", "icon": "mira",
         "state": "on" if detail.exact else "off"},
    ]
