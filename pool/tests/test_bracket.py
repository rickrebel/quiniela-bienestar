"""Tests de la resolución del cruce de eliminatoria (``bracket``).

Lógica pura sobre instancias en memoria (sin BD): ``winner_team``,
``loser_team`` y ``resolve_sources`` con los índices de origen y
predicciones inyectados."""

from django.test import SimpleTestCase

from pool.models import Prediction
from pool.services.bracket import (
    Contender, loser_team, resolve_sources, winner_team)
from tournament.models import Match, Team

BRA = Team(id=1, fifa_code="BRA", name_es="Brasil")
ARG = Team(id=2, fifa_code="ARG", name_es="Argentina")


def source(number, **kw):
    """Partido origen en memoria; BRA local y ARG visitante por defecto."""
    kw.setdefault("home_team", BRA)
    kw.setdefault("away_team", ARG)
    return Match(of_number=number, **kw)


def target(number, home_ph="", away_ph=""):
    """Partido destino con sus slots como placeholder (FK vacío)."""
    return Match(
        of_number=number, home_placeholder=home_ph, away_placeholder=away_ph)


class WinnerTeamTests(SimpleTestCase):
    def test_home_wins_on_goals(self):
        m = source(74, status="FINISHED", home_goals=2, away_goals=0)
        self.assertIs(winner_team(m), BRA)

    def test_away_wins_on_goals(self):
        m = source(74, status="FINISHED", home_goals=0, away_goals=1)
        self.assertIs(winner_team(m), ARG)

    def test_not_finished_is_none(self):
        m = source(74, status="SCHEDULED", home_goals=None, away_goals=None)
        self.assertIsNone(winner_team(m))

    def test_penalty_shootout_uses_penalties(self):
        m = source(
            74, status="FINISHED", home_goals=1, away_goals=1,
            decided_by=Match.PENALTY_SHOOTOUT,
            home_penalties=2, away_penalties=4)
        self.assertIs(winner_team(m), ARG)

    def test_draw_without_penalties_is_none(self):
        m = source(74, status="FINISHED", home_goals=1, away_goals=1)
        self.assertIsNone(winner_team(m))

    def test_missing_team_is_none(self):
        m = source(
            74, status="FINISHED", home_goals=2, away_goals=0, away_team=None)
        self.assertIsNone(winner_team(m))

    def test_loser_is_the_other_team(self):
        m = source(101, status="FINISHED", home_goals=2, away_goals=0)
        self.assertIs(loser_team(m), ARG)


class ResolveSourcesTests(SimpleTestCase):
    def _resolve(self, targets, sources, preds=None):
        resolve_sources(
            targets, user=None, quiniela=None,
            source_by_number={s.of_number: s for s in sources},
            preds_by_match=preds or {},
        )

    def test_winner_fills_team(self):
        t = target(89, home_ph="W74", away_ph="W77")
        src = source(74, status="FINISHED", home_goals=2, away_goals=0)
        self._resolve([t], [src])
        self.assertIs(t.home_team, BRA)
        self.assertFalse(hasattr(t, "home_contenders"))

    def test_contenders_highlight_predicted_winner(self):
        t = target(89, home_ph="W74")
        src = source(74)  # sin resultado, ambos equipos en BD
        src.id = 740
        pred = Prediction(match_id=740, home_goals=2, away_goals=1)
        self._resolve([t], [src], {740: pred})
        self.assertIsNone(t.home_team)
        self.assertEqual(
            t.home_contenders,
            [Contender(BRA, True), Contender(ARG, False)])

    def test_contenders_without_prediction_highlight_none(self):
        t = target(89, home_ph="W74")
        src = source(74)
        src.id = 740
        self._resolve([t], [src])
        self.assertEqual(
            t.home_contenders,
            [Contender(BRA, False), Contender(ARG, False)])

    def test_no_contenders_when_source_lacks_team(self):
        t = target(89, home_ph="W74")
        src = source(74, away_team=None)
        src.id = 740
        self._resolve([t], [src])
        self.assertIsNone(t.home_team)
        self.assertFalse(hasattr(t, "home_contenders"))

    def test_loser_slot_highlights_predicted_loser(self):
        # 3.er lugar: "L101" realza a quien el jugador estimó que CAE.
        t = target(103, home_ph="L101")
        src = source(101)
        src.id = 1010
        pred = Prediction(match_id=1010, home_goals=2, away_goals=1)  # BRA
        self._resolve([t], [src], {1010: pred})
        self.assertEqual(
            t.home_contenders,
            [Contender(BRA, False), Contender(ARG, True)])

    def test_group_placeholder_is_ignored(self):
        t = target(73, home_ph="2A", away_ph="2B")
        self._resolve([t], [])
        self.assertIsNone(t.home_team)
        self.assertFalse(hasattr(t, "home_contenders"))
