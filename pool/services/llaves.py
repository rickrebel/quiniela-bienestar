"""Datos del bracket (llaves) del Mundial para la vista ``/<slug>/llaves/``.

Se arma **desde la BD**: los 16 partidos de dieciseisavos (fase ``LAST_32``)
con sus equipos, banderas y marcadores reales, más el ganador de cada uno (que
sube a la ranura de octavos). Nada inventado: si el cruce aún no está definido
se muestra el origen textual del equipo (placeholder de OF, p. ej. ``"2A"``,
``"3A/B/C/D/F"``) y sin bandera.

El **orden** de la lista es el que consume el layout radial de ``llaves.js``
(alas de 4 partidos: los pares adyacentes alimentan el mismo octavo). Se deriva
del árbol real recorriendo los placeholders ``W##`` desde la final hacia las
hojas (``_leaf_order``), de modo que las conexiones del árbol quedan correctas
sin cablearlas a mano.
"""

from __future__ import annotations

from django.templatetags.static import static

from pool.services.bracket import SOURCE_RE, winner_team
from tournament.models import Match, Stage


def _team(team, placeholder: str) -> dict:
    """Equipo para el nodo: real (con bandera) o su origen textual.

    Si el FK está en BD devuelve nombre + bandera; si el cruce aún no se
    define, expone el placeholder de OF como nombre y sin bandera."""
    if team is not None:
        # HD (80px webp) sólo en esta vista; el resto usa Team.flag_path (40px).
        flag = f"flags_80/{team.flag_code}.webp" if team.flag_code else ""
        return {
            "code": team.flag_code,
            "name": team.name_es or team.name,
            "flag_url": static(flag) if flag else "",
        }
    return {"name": placeholder or "", "flag_url": ""}


def _winner(match: Match) -> dict | None:
    """Equipo que avanza a octavos, o ``None`` si el partido no está resuelto."""
    team = winner_team(match)
    return _team(team, "") if team is not None else None


def _leaf_order(by_num: dict[int, Match], of_number: int) -> list[int]:
    """Orden de las hojas (of_number de LAST_32) bajo un nodo del árbol.

    Recorre los placeholders ``W##`` (local y luego visitante) hacia abajo;
    en un partido de dieciseisavos devuelve su propio número. El resultado es
    justo el orden que espera el layout de alas de ``llaves.js``."""
    match = by_num.get(of_number)
    if match is None:
        return []
    if match.stage.key == Stage.LAST_32:
        return [of_number]
    order: list[int] = []
    for placeholder in (match.home_placeholder, match.away_placeholder):
        matched = SOURCE_RE.match(placeholder or "")
        if matched and matched.group(1) == "W":
            order.extend(_leaf_order(by_num, int(matched.group(2))))
    return order


def build_bracket() -> dict:
    """Payload JSON-able para ``llaves.js`` (vía ``json_script``).

    Toma de la BD los 16 dieciseisavos ordenados por el árbol real y resuelve
    equipos/banderas/marcadores y el ganador que sube a octavos.
    """
    ko_keys = [
        Stage.LAST_32, Stage.LAST_16, Stage.QUARTER_FINALS,
        Stage.SEMI_FINALS, Stage.FINAL,
    ]
    by_num = {
        m.of_number: m
        for m in Match.objects.filter(stage__key__in=ko_keys).select_related(
            "stage", "home_team", "away_team"
        )
    }

    order = _leaf_order(by_num, Match.FINAL_NUMBER)
    if len(order) != 16:
        # Respaldo: árbol incompleto → los LAST_32 por número de partido.
        order = sorted(
            n for n, m in by_num.items() if m.stage.key == Stage.LAST_32
        )

    matches = []
    for number in order:
        m = by_num[number]
        played = m.status == "FINISHED" and m.home_goals is not None
        matches.append(
            {
                "home": _team(m.home_team, m.home_placeholder),
                "away": _team(m.away_team, m.away_placeholder),
                "played": played,
                "home_goals": m.home_goals,
                "away_goals": m.away_goals,
                "winner": _winner(m),
            }
        )
    return {"matches": matches}
