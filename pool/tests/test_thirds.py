"""Tests del ranking de los mejores terceros (``build_thirds``)."""

from django.test import SimpleTestCase

from pool.services import anexo_c
from pool.services.anexo_c import assign_thirds
from pool.services.standings import (
    VARIANTS, GroupStandings, StandingRow, VariantTable,
)
from pool.services.thirds import ThirdRow, build_thirds
from pool.views.stages import _build_thirds_simulator
from tournament.models import Match, Team

_tid = iter(range(1, 1000))


def _row(points: int, **kwargs) -> StandingRow:
    return StandingRow(team=Team(id=next(_tid)), points=points, **kwargs)


def _group(letter: str, third_points: int, **third_kwargs) -> GroupStandings:
    """Grupo con 3 filas; la 3.ª es el tercero a evaluar. Las mismas filas
    en las tres variantes (a estos tests solo les importa el orden)."""
    def rows() -> list[StandingRow]:
        third = StandingRow(
            team=Team(id=next(_tid), name_es=letter), points=third_points,
            **third_kwargs,
        )
        return [_row(20), _row(15), third]

    tables = [VariantTable(variant=v, rows=rows()) for v in VARIANTS]
    return GroupStandings(group=letter, tables=tables, teams=[])


class BuildThirdsTests(SimpleTestCase):
    def _standings(self) -> dict[str, GroupStandings]:
        points = {
            "A": 5, "B": 5, "C": 4, "D": 4, "E": 3, "F": 3,
            "G": 2, "H": 2, "I": 1, "J": 1, "K": 0, "L": 0,
        }
        return {g: _group(g, p) for g, p in points.items()}

    def test_orders_twelve_thirds_by_points(self):
        thirds = build_thirds(self._standings())["mix"]
        self.assertEqual(len(thirds), 12)
        self.assertEqual([t.group for t in thirds],
                         list("ABCDEFGHIJKL"))

    def test_top_eight_qualify(self):
        thirds = build_thirds(self._standings())["mix"]
        self.assertEqual([t.group for t in thirds if t.qualified],
                         list("ABCDEFGH"))
        self.assertEqual(sum(t.qualified for t in thirds), 8)

    def test_goal_diff_breaks_points_tie(self):
        # E y F empatan a 3 pts; F tiene mejor DG y debe quedar antes.
        standings = self._standings()
        standings["F"] = _group("F", 3, goals_for=5, goals_against=1)
        thirds = build_thirds(standings)["mix"]
        order = [t.group for t in thirds]
        self.assertLess(order.index("F"), order.index("E"))


class ThirdsSimulatorTests(SimpleTestCase):
    """Payload del simulador "¿qué pasaría si...?" de dieciseisavos."""

    def _thirds(self) -> list[ThirdRow]:
        """12 terceros A-L; clasifican los 8 grupos de ``WINNER_SLOTS``."""
        qualified = set(anexo_c.WINNER_SLOTS)
        return [
            ThirdRow(
                team=Team(id=i, name_es=f"Eq {g}"),
                group=g, points=0, goal_diff=0, goals_for=0,
                yellow=0, red=0, qualified=g in qualified,
            )
            for i, g in enumerate("ABCDEFGHIJKL", start=1)
        ]

    def _matches(self) -> list[Match]:
        """Un partido por slot de ganador (1A, 1B, …) con un tercero como
        visitante; el No. arranca en 73 (dieciseisavos)."""
        return [
            Match(
                id=100 + i, of_number=73 + i,
                home_placeholder=f"1{w}", away_placeholder="3A/B/C",
            )
            for i, w in enumerate(anexo_c.WINNER_SLOTS)
        ]

    def test_payload_shape(self):
        payload = _build_thirds_simulator(self._thirds(), self._matches())
        self.assertEqual(payload["winner_slots"], anexo_c.WINNER_SLOTS)
        self.assertIs(payload["combinations"], anexo_c.COMBINATIONS)
        self.assertEqual(len(payload["matches"]), len(anexo_c.WINNER_SLOTS))
        self.assertEqual(
            [m["winner_group"] for m in payload["matches"]],
            anexo_c.WINNER_SLOTS,
        )
        self.assertEqual(len(payload["thirds"]), 12)

    def test_match_number_matches_anexo_c(self):
        thirds = self._thirds()
        _build_thirds_simulator(thirds, self._matches())
        mapping = assign_thirds(set(anexo_c.WINNER_SLOTS))
        # Cada partido (No. 73+i) alimenta al tercero mapping[1{w}].
        expected = {
            mapping[w]: 73 + i
            for i, w in enumerate(anexo_c.WINNER_SLOTS)
        }
        for t in thirds:
            if t.qualified:
                self.assertEqual(t.match_number, expected[t.group])
            else:
                self.assertIsNone(t.match_number)
