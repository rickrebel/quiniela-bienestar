"""Tests de la cadena de avance del bracket (``services/llaves.py``).

Lógica pura sobre nodos en memoria (sin BD): ``_advancers`` debe anclar
cada slot al avance REAL del hijo cuando ya se conoce (los pronósticos y
``advancing_team`` se capturan contra los equipos reales) y solo caer a
la cadena pronosticada mientras no haya resultado."""

from django.test import SimpleTestCase

from pool.models import Prediction
from pool.services.llaves import _advancers
from tournament.models import Match, Team

FRA = Team(id=1, fifa_code="FRA", name_es="Francia")
SEN = Team(id=2, fifa_code="SEN", name_es="Senegal")
BRA = Team(id=3, fifa_code="BRA", name_es="Brasil")
ARG = Team(id=4, fifa_code="ARG", name_es="Argentina")


def leaf(match_id, home, away, **kw):
    """Nodo hoja (16avos) con su partido en memoria."""
    kw.setdefault("status", "TIMED")
    m = Match(id=match_id, home_team=home, away_team=away, **kw)
    return {"match": m, "children": []}


def node(match_id, children, **kw):
    """Nodo interno (octavos+) sobre los avances de sus hijos."""
    kw.setdefault("status", "TIMED")
    m = Match(id=match_id, **kw)
    return {"match": m, "children": children}


class AdvancersTests(SimpleTestCase):
    def setUp(self):
        # Hoja jugada: el jugador predijo FRA, pero ganó SEN.
        self.played = leaf(
            201, FRA, SEN, status="FINISHED", home_goals=0, away_goals=1)
        # Hoja pendiente: el jugador predice que avanza ARG.
        self.pending = leaf(202, BRA, ARG)
        self.octavos = node(210, [self.played, self.pending])
        self.preds = {
            201: Prediction(home_goals=2, away_goals=0),  # FRA (falló)
            202: Prediction(home_goals=0, away_goals=1),  # ARG
        }

    def test_leaf_pick_follows_prediction(self):
        real, pick = _advancers(self.pending, self.preds)
        self.assertIsNone(real)
        self.assertIs(pick, ARG)

    def test_leaf_real_winner_ignores_failed_pick(self):
        real, pick = _advancers(self.played, self.preds)
        self.assertIs(real, SEN)
        self.assertIs(pick, FRA)

    def test_slot_reanchors_to_real_winner(self):
        # Octavos "gana el local": el slot local ya es SEN en la realidad;
        # debe avanzar SEN, no la cadena vieja (FRA).
        self.preds[210] = Prediction(home_goals=1, away_goals=0)
        _, pick = _advancers(self.octavos, self.preds)
        self.assertIs(pick, SEN)

    def test_draw_advancing_team_matches_real_contender(self):
        # Empate + pick de penales: advancing_team guarda un equipo REAL
        # (validado en save_prediction); debe casar con el slot re-anclado.
        self.preds[210] = Prediction(
            home_goals=1, away_goals=1, advancing_team=SEN)
        _, pick = _advancers(self.octavos, self.preds)
        self.assertIs(pick, SEN)

    def test_pending_slot_falls_back_to_predicted_chain(self):
        # El slot visitante aún no se define: vale la cadena pronosticada.
        self.preds[210] = Prediction(home_goals=0, away_goals=1)
        _, pick = _advancers(self.octavos, self.preds)
        self.assertIs(pick, ARG)

    def test_draw_advancing_team_outside_contenders_is_none(self):
        # Pick de penales que no encaja con ningún contendiente → None.
        self.preds[210] = Prediction(
            home_goals=1, away_goals=1, advancing_team=BRA)
        _, pick = _advancers(self.octavos, self.preds)
        self.assertIsNone(pick)

    def test_no_prediction_is_none(self):
        _, pick = _advancers(self.octavos, self.preds)
        self.assertIsNone(pick)
