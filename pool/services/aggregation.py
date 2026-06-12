"""Agregación colectiva de predicciones ("Ignorancia colectiva").

Método: media recortada de goles por equipo + matriz de Poisson.
La media recortada descarta extremos sin perder eficiencia (Jose &
Winkler 2008); usar las medias como λ de dos Poisson independientes
aprovecha los decimales que el redondeo destruiría y produce además la
probabilidad de cada marcador. Ver collective_intelligence/.
"""

import math
from dataclasses import dataclass

TRIM_RATIO = 0.10
MAX_GOALS = 10
VIRTUAL_EMAIL = "rickrebel+ignorancia@gmail.com"
VIRTUAL_NAME = "Ignorancia colectiva"


@dataclass(frozen=True)
class AggregateResult:
    """Marcador agregado de un partido, con su evidencia.

    ``ranked`` trae todas las celdas (home, away, prob) ordenadas por
    probabilidad descendente, para reportes y futura visualización.
    """

    home_goals: int
    away_goals: int
    lam_home: float
    lam_away: float
    ranked: list[tuple[int, int, float]]


def trimmed_mean(values: list[int], ratio: float = TRIM_RATIO) -> float:
    """Media tras descartar ``floor(n*ratio)`` valores por cada cola.

    Con 31 predicciones y ratio 0.10 recorta 3 por lado (quedan 25);
    con muestras chicas el recorte es 0 y degrada a media simple.
    """
    if not values:
        raise ValueError("trimmed_mean requiere al menos un valor")
    cut = int(len(values) * ratio)
    kept = sorted(values)[cut:len(values) - cut]
    return sum(kept) / len(kept)


def _poisson(lam: float, k: int) -> float:
    """P(X = k) para X ~ Poisson(λ)."""
    return lam ** k * math.exp(-lam) / math.factorial(k)


def poisson_matrix(
    lam_home: float, lam_away: float, max_goals: int = MAX_GOALS
) -> list[list[float]]:
    """Matriz ``P[i][j]`` = P(local anota i) · P(visita anota j)."""
    home = [_poisson(lam_home, k) for k in range(max_goals + 1)]
    away = [_poisson(lam_away, k) for k in range(max_goals + 1)]
    return [[ph * pa for pa in away] for ph in home]


def _sign_probs(matrix: list[list[float]]) -> dict[int, float]:
    """Probabilidad acumulada por signo: 1 local, 0 empate, -1 visita."""
    probs = {1: 0.0, 0: 0.0, -1: 0.0}
    for h, row in enumerate(matrix):
        for a, p in enumerate(row):
            probs[(h > a) - (h < a)] += p
    return probs


def aggregate_score(
    home_preds: list[int], away_preds: list[int]
) -> AggregateResult:
    """Marcador agregado de la multitud para un partido.

    El marcador es la celda más probable de la matriz. Empates de
    probabilidad (entrada simétrica) se resuelven por: (1) signo con
    más probabilidad acumulada — vale 3 de los 5 puntos del pool y los
    empates no reciben bono de diferencia, así que un signo le gana al
    empate —; (2) preferencia por el local, convención determinista
    para un volado real.
    """
    lam_home = trimmed_mean(home_preds)
    lam_away = trimmed_mean(away_preds)
    matrix = poisson_matrix(lam_home, lam_away)
    signs = _sign_probs(matrix)

    cells = [
        (h, a, p)
        for h, row in enumerate(matrix)
        for a, p in enumerate(row)
    ]
    best = max(cells, key=lambda c: (c[2], signs[_sign(c)], c[0] - c[1]))
    ranked = sorted(cells, key=lambda c: c[2], reverse=True)
    return AggregateResult(
        home_goals=best[0],
        away_goals=best[1],
        lam_home=lam_home,
        lam_away=lam_away,
        ranked=ranked,
    )


def _sign(cell: tuple[int, int, float]) -> int:
    h, a, _ = cell
    return (h > a) - (h < a)
