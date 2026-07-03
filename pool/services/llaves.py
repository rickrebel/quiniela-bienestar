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

from pool.models import Prediction, Quiniela, User
from pool.services.bracket import SOURCE_RE, winner_team
from tournament.models import Match, Stage, Team


def _team(team, placeholder: str) -> dict:
    """Equipo para el nodo: real (con bandera) o su origen textual.

    Si el FK está en BD devuelve nombre + bandera; si el cruce aún no se
    define, expone el placeholder de OF como nombre y sin bandera."""
    if team is not None:
        # HD (80px webp) sólo en esta vista; el resto usa Team.flag_path (40px).
        flag = f"flags_80/{team.flag_code}.webp" if team.flag_code else ""
        return {
            "id": team.id,
            "code": team.flag_code,
            "name": team.name_es or team.name,
            "flag_url": static(flag) if flag else "",
        }
    return {"name": placeholder or "", "flag_url": ""}


def _winner(match: Match) -> dict | None:
    """Equipo que avanza a octavos, o ``None`` si el partido no está resuelto."""
    team = winner_team(match)
    return _team(team, "") if team is not None else None


def _predicted(match: Match, pred: Prediction | None) -> dict | None:
    """Pronóstico del jugador para un dieciseisavos.

    Devuelve su marcador estimado y la bandera del equipo que cree que
    avanza (para pintar el slot de octavos aún sin resultado real). ``None``
    si no hay pronóstico. El avance sale de ``_pred_pick`` (misma regla que el
    resto del árbol), así la lógica no se bifurca."""
    if pred is None or pred.home_goals is None:
        return None
    winner = _pred_pick(pred, match.home_team, match.away_team)
    return {
        "home_goals": pred.home_goals,
        "away_goals": pred.away_goals,
        "winner": _team(winner, "") if winner is not None else None,
    }


def _pred_pick(
    pred: Prediction | None, home: Team | None, away: Team | None
) -> Team | None:
    """Equipo que el jugador pronostica que avanza, dados sus 2 contendientes
    pronosticados: el de más goles, o su pick de penales (``advancing_team``)
    si empató. ``None`` si no hay pronóstico o su avance no encaja con los
    contendientes (p. ej. la cadena de pronóstico no llega hasta aquí)."""
    if pred is None or pred.home_goals is None:
        return None
    if pred.home_goals > pred.away_goals:
        return home
    if pred.away_goals > pred.home_goals:
        return away
    picked = pred.advancing_team
    if picked is None:
        return None
    if home is not None and picked.id == home.id:
        return home
    if away is not None and picked.id == away.id:
        return away
    return None


def _tree(by_num: dict[int, Match], of_number: int) -> dict | None:
    """Nodo del árbol de eliminatoria: el partido y (recursivo) sus 2 hijos,
    las fuentes ``W##`` de sus dos ranuras (hijo local primero). Los
    dieciseisavos son hojas. Mismo recorrido que ``_leaf_order`` → los grupos
    del árbol quedan alineados con las rebanadas de la lista ``matches``."""
    match = by_num.get(of_number)
    if match is None:
        return None
    node: dict = {"match": match, "children": []}
    if match.stage.key == Stage.LAST_32:
        return node
    for placeholder in (match.home_placeholder, match.away_placeholder):
        matched = SOURCE_RE.match(placeholder or "")
        if matched and matched.group(1) == "W":
            child = _tree(by_num, int(matched.group(2)))
            if child is not None:
                node["children"].append(child)
    return node


def _advancers(
    node: dict, preds: dict[int, Prediction]
) -> tuple[Team | None, Team | None]:
    """``(real, pronosticado)`` equipo que avanza de este partido.

    ``real`` = ganador ya conocido (``winner_team``). ``pronosticado`` = el
    que el jugador pasa entre los 2 contendientes de sus slots: el avance
    REAL del hijo si ya se conoce (el pronóstico se capturó contra los
    equipos reales, y ``advancing_team`` se valida contra ellos), o su
    avance pronosticado mientras no haya resultado. ``None`` si la cadena
    no llega hasta aquí."""
    match = node["match"]
    real = winner_team(match)
    children = node["children"]
    if children:
        home_real, home_pick = _advancers(children[0], preds)
        home_pred = home_real if home_real is not None else home_pick
        if len(children) > 1:
            away_real, away_pick = _advancers(children[1], preds)
            away_pred = away_real if away_real is not None else away_pick
        else:
            away_pred = None
    else:
        home_pred, away_pred = match.home_team, match.away_team
    picked = _pred_pick(preds.get(match.id), home_pred, away_pred)
    return real, picked


def _score(match: Match, preds: dict[int, Prediction]) -> dict | None:
    """Marcador de un partido para pintarlo sobre su par de círculos: el real
    si ya se jugó (``played=True``), o el pronosticado por el jugador si no
    (``played=False``). ``home``/``away`` quedan orientados como el partido en
    BD (``home`` = primer círculo del par). ``None`` si no hay ninguno."""
    if match.status == "FINISHED" and match.home_goals is not None:
        data = {
            "home": match.home_goals, "away": match.away_goals,
            "played": True,
        }
        # Empate resuelto por penales: el marcador no delata al que avanzó,
        # así que se adjunta su code para pintar su número en dorado
        # (llaves.js), aunque ambos números sean iguales.
        if (match.home_goals == match.away_goals
                and match.decided_by == Match.PENALTY_SHOOTOUT):
            win = winner_team(match)
            if win is not None:
                data["pen_winner"] = win.flag_code
        return data
    pred = preds.get(match.id)
    if pred is not None and pred.home_goals is not None:
        return {
            "home": pred.home_goals, "away": pred.away_goals,
            "played": False,
        }
    return None


def _slot(node: dict, preds: dict[int, Prediction]) -> dict:
    """Ranura de fase avanzada: banderas de avance (real / estimada) y el
    marcador (real o pronosticado) del propio partido del nodo."""
    real, pred = _advancers(node, preds)
    return {
        "real": _team(real, "") if real is not None else None,
        "pred": _team(pred, "") if pred is not None else None,
        "score": _score(node["match"], preds),
    }


def _tree_payload(root: dict, preds: dict[int, Prediction]) -> dict | None:
    """Avances (real/estimado) de octavos→final para pintar las fases sin
    marcador. Alineado con los 4 grupos-de-4 del layout radial (orden del
    árbol): ``cuartos[i]`` (grupo Gi) trae ``octavos`` (avance de sus 2
    partidos de octavos → llenan los 2 círculos del cuarto) y ``cuarto``
    (avance del cuarto → llena un círculo de semifinal); ``semis[k]`` es el
    avance de cada semifinal (llena un círculo de la final). ``None`` si el
    árbol no tiene la forma esperada (final → 2 semis → 2 cuartos c/u)."""
    semis = root["children"]
    if len(semis) != 2 or any(len(s["children"]) != 2 for s in semis):
        return None
    cuarto_nodes = semis[0]["children"] + semis[1]["children"]
    groups = []
    for cuarto in cuarto_nodes:
        octavos = cuarto["children"]
        if len(octavos) != 2:
            return None
        groups.append({
            "octavos": [
                _slot(octavos[0], preds),
                _slot(octavos[1], preds),
            ],
            "cuarto": _slot(cuarto, preds),
        })
    return {
        "cuartos": groups,
        "semis": [
            _slot(semis[0], preds),
            _slot(semis[1], preds),
        ],
        "final": _score(root["match"], preds),
    }


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


def build_bracket(user: User, quiniela: Quiniela) -> dict:
    """Payload JSON-able para ``llaves.js`` (vía ``json_script``).

    Toma de la BD los 16 dieciseisavos ordenados por el árbol real y resuelve
    equipos/banderas/marcadores y el ganador que sube a octavos. Adjunta, por
    partido, el pronóstico del jugador (``pred``) para pintar el marcador
    estimado y la bandera de su avance mientras no haya resultado real.
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

    preds_by_match = {
        p.match_id: p
        for p in Prediction.objects.filter(
            user=user, quiniela=quiniela,
            match_id__in=[m.id for m in by_num.values()],
        ).select_related("advancing_team")
    }

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
                "pred": _predicted(m, preds_by_match.get(m.id)),
            }
        )

    # Fases sin marcador (cuartos→final): avance real/estimado por ranura.
    tree = None
    if len(order) == 16:
        root = _tree(by_num, Match.FINAL_NUMBER)
        if root is not None:
            tree = _tree_payload(root, preds_by_match)

    return {"matches": matches, "tree": tree}
