"""Anexo C: combinaciones de los 8 mejores terceros del Mundial 2026.

La tabla (495 combinaciones) define, según QUÉ 8 grupos aportan un tercero
clasificado, contra qué tercero juega cada ganador de grupo en dieciseisavos.
Es dato de referencia estático: se lee del JSON generado por el comando
``extract_anexo_c`` (sin BD). Ver ``pool.services.thirds`` para el ranking que
decide los 8 clasificados.
"""

import json
from pathlib import Path

_DATA = json.loads(
    (Path(__file__).parent / "data" / "anexo_c.json").read_text("utf-8")
)
WINNER_SLOTS: list[str] = _DATA["winner_slots"]
# Pública para el simulador cliente (lo replica en JS); el lookup server-side
# usa la misma vía ``assign_thirds``.
COMBINATIONS: dict[str, dict[str, str]] = _DATA["combinations"]
_COMBINATIONS = COMBINATIONS


def assign_thirds(qualified: set[str]) -> dict[str, str] | None:
    """Mapa ``grupo_ganador -> grupo del tercero`` para los 8 grupos cuyos
    terceros clasificaron. Devuelve ``None`` si el conjunto no es una
    combinación válida (p. ej. aún no hay 8 terceros firmes)."""
    if len(qualified) != len(WINNER_SLOTS):
        return None
    return _COMBINATIONS.get("".join(sorted(qualified)))
