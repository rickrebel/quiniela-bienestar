"""Context processors de la quiniela."""

import logging

from pool.services.leaderboard import build_leaderboard

logger = logging.getLogger(__name__)


def standing(request) -> dict:
    """Posición y puntos del usuario para el rank-chip del header.

    Corre en TODOS los templates (admin y login incluidos): debe
    degradar a {} ante cualquier problema, nunca tumbar la página.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    try:
        board = build_leaderboard()
        return {
            "my_standing": board.row_for(user),
            "board_max": board.max_points,
        }
    except Exception:
        logger.exception("No se pudo calcular el standing del usuario")
        return {}
