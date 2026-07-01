"""Datos del bracket (llaves) del Mundial para la vista ``/<slug>/llaves/``.

Mantenido **a mano**: ``LAST_32_MATCHES`` es la lista de los 16 partidos de
dieciseisavos (LAST_32, "16avos") con sus resultados conforme se van jugando.
No se sincroniza con el modelo ``Match`` (los placeholders y la captura de
resultados viven aparte); aquí se transcriben los marcadores reales para
dibujar el árbol radial.

Orden de la lista = el que consume el layout radial de ``llaves.js``: los
primeros 8 partidos forman las dos alas superiores (izquierda y derecha) y los
últimos 8 las dos inferiores, en grupos de 4. El **ganador** de cada partido
sube a la ranura de octavos (depth-2) de su ala.

Cada partido:
    {
        "home": ("br", "Brasil"),      # (flag_code, nombre_es)
        "away": ("sn", "Senegal"),
        "played": True,
        "home_goals": 3, "away_goals": 0,
        "advancing": None,             # flag_code del que pasa si fue empate
                                       # (penales); None si se definió en cancha
        "venue": "MetLife Stadium",
        "date": "",                    # texto si aún no se juega
    }

Para actualizar tras un partido: pon ``played=True`` con el marcador; si fue
empate definido por penales, pon ``advancing`` con el código del que avanza.
"""

from __future__ import annotations

from django.templatetags.static import static


# NOTE: datos ilustrativos de ejemplo — reemplazar con el bracket/resultados
# reales conforme se jueguen. Brasil, Canadá y Paraguay quedan ya marcados como
# clasificados a octavos a modo de muestra de la vista.
LAST_32_MATCHES: list[dict] = [
    # --- Ala superior izquierda ---
    {"home": ("br", "Brasil"), "away": ("sn", "Senegal"), "played": True,
     "home_goals": 3, "away_goals": 0, "advancing": None,
     "venue": "MetLife Stadium", "date": ""},
    {"home": ("ar", "Argentina"), "away": ("fr", "Francia"), "played": False,
     "home_goals": None, "away_goals": None, "advancing": None,
     "venue": "SoFi Stadium", "date": "5 Jul, 20:00"},
    {"home": ("de", "Alemania"), "away": ("es", "España"), "played": True,
     "home_goals": 1, "away_goals": 1, "advancing": "de",
     "venue": "AT&T Stadium (4-3 pen)", "date": ""},
    {"home": ("gb-eng", "Inglaterra"), "away": ("pt", "Portugal"), "played": False,
     "home_goals": None, "away_goals": None, "advancing": None,
     "venue": "Hard Rock Stadium", "date": "5 Jul, 16:00"},
    # --- Ala superior derecha ---
    {"home": ("nl", "Países Bajos"), "away": ("be", "Bélgica"), "played": True,
     "home_goals": 1, "away_goals": 0, "advancing": None,
     "venue": "Lincoln Financial", "date": ""},
    {"home": ("hr", "Croacia"), "away": ("it", "Italia"), "played": False,
     "home_goals": None, "away_goals": None, "advancing": None,
     "venue": "Arrowhead Stadium", "date": "6 Jul, 13:00"},
    {"home": ("uy", "Uruguay"), "away": ("co", "Colombia"), "played": True,
     "home_goals": 0, "away_goals": 1, "advancing": None,
     "venue": "Mercedes-Benz", "date": ""},
    {"home": ("ca", "Canadá"), "away": ("mx", "México"), "played": True,
     "home_goals": 2, "away_goals": 1, "advancing": None,
     "venue": "BC Place", "date": ""},
    # --- Ala inferior izquierda ---
    {"home": ("py", "Paraguay"), "away": ("eg", "Egipto"), "played": True,
     "home_goals": 1, "away_goals": 0, "advancing": None,
     "venue": "NRG Stadium", "date": ""},
    {"home": ("jp", "Japón"), "away": ("kr", "Corea del Sur"), "played": False,
     "home_goals": None, "away_goals": None, "advancing": None,
     "venue": "Levi's Stadium", "date": "6 Jul, 19:00"},
    {"home": ("gh", "Ghana"), "away": ("ng", "Nigeria"), "played": True,
     "home_goals": 1, "away_goals": 3, "advancing": None,
     "venue": "Estadio Akron", "date": ""},
    {"home": ("ec", "Ecuador"), "away": ("au", "Australia"), "played": False,
     "home_goals": None, "away_goals": None, "advancing": None,
     "venue": "Gillette Stadium", "date": "7 Jul, 20:00"},
    # --- Ala inferior derecha ---
    {"home": ("dk", "Dinamarca"), "away": ("no", "Noruega"), "played": True,
     "home_goals": 2, "away_goals": 1, "advancing": None,
     "venue": "Estadio Azteca", "date": ""},
    {"home": ("dz", "Argelia"), "away": ("ba", "Bosnia"), "played": False,
     "home_goals": None, "away_goals": None, "advancing": None,
     "venue": "GEHA Field", "date": "7 Jul, 16:00"},
    {"home": ("ie", "Irlanda"), "away": ("ma", "Marruecos"), "played": False,
     "home_goals": None, "away_goals": None, "advancing": None,
     "venue": "Lumen Field", "date": "8 Jul, 13:00"},
    {"home": ("us", "Estados Unidos"), "away": ("ch", "Suiza"), "played": True,
     "home_goals": 2, "away_goals": 2, "advancing": "us",
     "venue": "Estadio BBVA (5-4 pen)", "date": ""},
]


def _team(pair: tuple[str, str]) -> dict:
    code, name = pair
    return {"code": code, "name": name, "flag_url": static(f"flags_40/{code}.png")}


def _winner(match: dict) -> dict | None:
    """Equipo que avanza a octavos, o ``None`` si el partido no se ha jugado.

    Se define por marcador; en empate (penales) por ``advancing``.
    """
    if not match["played"]:
        return None
    hg, ag = match["home_goals"], match["away_goals"]
    if hg is None or ag is None:
        return None
    if hg > ag:
        return _team(match["home"])
    if ag > hg:
        return _team(match["away"])
    adv = match.get("advancing")
    if adv == match["home"][0]:
        return _team(match["home"])
    if adv == match["away"][0]:
        return _team(match["away"])
    return None


def build_bracket() -> dict:
    """Payload JSON-able para ``llaves.js`` (vía ``json_script``).

    Resuelve banderas estáticas y el ganador de cada partido (que sube a la
    ranura de octavos). ``llaves.js`` parte ``matches`` en alas (8 + 8).
    """
    matches = []
    for m in LAST_32_MATCHES:
        matches.append(
            {
                "home": _team(m["home"]),
                "away": _team(m["away"]),
                "played": m["played"],
                "home_goals": m["home_goals"],
                "away_goals": m["away_goals"],
                "venue": m["venue"],
                "date": m["date"],
                "winner": _winner(m),
            }
        )
    return {"matches": matches}
