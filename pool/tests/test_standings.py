"""Tests de la tabla de posiciones por grupo (tres variantes).

El fixture del grupo A está diseñado para que el orden final sea
distinto en cada variante: real [MEX, USA, JAM, CAN], est
[CAN, JAM, USA, MEX] y mix [JAM, MEX, CAN, USA]; así un error de
fuente de datos en cualquier variante rompe su test.
"""

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from pool.models import Prediction, User
from pool.services.standings import (
    StandingRow, build_group_standings, rank_group,
)
from tournament.models import Match, Stadium, Stage, Team


def _trow(name: str = "X", **kwargs) -> StandingRow:
    return StandingRow(team=Team(name_es=name), **kwargs)


class SortKeyTests(SimpleTestCase):
    def _first(self, a: StandingRow, b: StandingRow) -> StandingRow:
        return min(a, b, key=lambda r: r.sort_key)

    def test_points_beat_goal_diff(self):
        worse_diff = _trow(points=6, goals_for=1, goals_against=5)
        better_diff = _trow(points=4, goals_for=9)
        self.assertIs(self._first(worse_diff, better_diff), worse_diff)

    def test_goal_diff_breaks_points_tie(self):
        wide = _trow(points=4, goals_for=5, goals_against=1)
        narrow = _trow(points=4, goals_for=9, goals_against=8)
        self.assertIs(self._first(narrow, wide), wide)

    def test_goals_for_breaks_diff_tie(self):
        high = _trow(points=4, goals_for=6, goals_against=4)
        low = _trow(points=4, goals_for=3, goals_against=1)
        self.assertIs(self._first(low, high), high)

    def test_fewer_reds_break_goals_tie(self):
        clean = _trow(points=4, goals_for=3, red=0, yellow=9)
        dirty = _trow(points=4, goals_for=3, red=1, yellow=0)
        self.assertIs(self._first(dirty, clean), clean)

    def test_fewer_yellows_break_reds_tie(self):
        clean = _trow(points=4, yellow=1)
        dirty = _trow(points=4, yellow=4)
        self.assertIs(self._first(dirty, clean), clean)

    # No necesitamos este test, no queremos en ningún caso que los equipos se ordenen alfabéticamente
    # def test_name_breaks_full_tie(self):
    #     zeta = _trow(name="Zambia")
    #     alfa = _trow(name="Argelia")
    #     self.assertIs(self._first(zeta, alfa), alfa)


class HeadToHeadTests(SimpleTestCase):
    """Desempate por enfrentamiento directo (regla FIFA 2026), sobre
    ``rank_group``. Los pares son (home_id, away_id, home_goals, away_goals).
    """

    @staticmethod
    def _row(tid: int, **kwargs) -> StandingRow:
        return StandingRow(team=Team(id=tid, name_es=str(tid)), **kwargs)

    @staticmethod
    def _ids(ordered: list[StandingRow]) -> list[int]:
        return [r.team.id for r in ordered]

    def test_direct_winner_breaks_points_tie(self):
        # Empate a pts y DG global; A le ganó 1-0 a B en el directo.
        a = self._row(1, points=3, goals_for=2, goals_against=1)
        b = self._row(2, points=3, goals_for=2, goals_against=1)
        self.assertEqual(self._ids(rank_group([b, a], [(1, 2, 1, 0)])),
                         [1, 2])

    def test_drawn_direct_falls_to_global(self):
        # El directo empató (1-1): no separa, decide GF global (B 3 > A 2).
        a = self._row(1, points=3, goals_for=2, goals_against=1)
        b = self._row(2, points=3, goals_for=3, goals_against=2)
        self.assertEqual(self._ids(rank_group([a, b], [(1, 2, 1, 1)])),
                         [2, 1])

    def test_three_way_mini_league(self):
        # A gana a B y C; B gana a C. Directo: A 6, B 3, C 0 pts.
        a = self._row(1, points=4)
        b = self._row(2, points=4)
        c = self._row(3, points=4)
        pairs = [(1, 2, 1, 0), (1, 3, 1, 0), (2, 3, 1, 0)]
        self.assertEqual(self._ids(rank_group([c, b, a], pairs)), [1, 2, 3])

    def test_full_tie_keeps_stable_order(self):
        # Sin partidos entre ellos y todo igual: orden estable (sin ranking
        # FIFA). El orden de entrada manda.
        a = self._row(1, points=3, goals_for=1, goals_against=1)
        b = self._row(2, points=3, goals_for=1, goals_against=1)
        self.assertEqual(self._ids(rank_group([a, b], [])), [1, 2])
        self.assertEqual(self._ids(rank_group([b, a], [])), [2, 1])


class BuildGroupStandingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.stage = Stage.objects.create(
            key="GROUP_STAGE", name="Fase de grupos", short_name="grupos",
            color="#4CAF50", order=1,
        )
        stadium = Stadium.objects.create(
            name="Estadio Azteca", city="CDMX", country="mx", utc_offset=-6,
        )
        cls.mex, cls.can, cls.usa, cls.jam = (
            Team.objects.create(
                name=name, name_es=name_es, fifa_code=code, group_name="A",
                confederation="concacaf",
            )
            for name, name_es, code in (
                ("Mexico", "México", "MEX"),
                ("Canada", "Canadá", "CAN"),
                ("USA", "Estados Unidos", "USA"),
                ("Jamaica", "Jamaica", "JAM"),
            )
        )
        # Grupo B: FINISHED sin goles y sin predicción (no debe contar
        # en ninguna variante).
        cls.bra = Team.objects.create(
            name="Brazil", name_es="Brasil", fifa_code="BRA",
            group_name="B", confederation="conmebol",
        )
        cls.arg = Team.objects.create(
            name="Argentina", name_es="Argentina", fifa_code="ARG",
            group_name="B", confederation="conmebol",
        )

        def match(num, home, away, **kwargs):
            return Match.objects.create(
                datetime=now, stage=cls.stage, stadium=stadium,
                home_team=home, away_team=away, of_number=num, **kwargs,
            )

        cls.m1 = match(1, cls.mex, cls.can, status="FINISHED",
                       home_goals=2, away_goals=0, home_yellow=1,
                       away_yellow=3, away_red=1)
        cls.m2 = match(2, cls.usa, cls.jam, status="FINISHED",
                       home_goals=1, away_goals=1)
        cls.m3 = match(3, cls.mex, cls.usa)
        cls.m4 = match(4, cls.can, cls.jam)
        cls.m5 = match(5, cls.mex, cls.jam)
        cls.m6 = match(6, cls.can, cls.usa)
        cls.m7 = match(7, cls.bra, cls.arg, status="FINISHED")

        cls.user = User.objects.create_user(
            "rick@x.com", first_name="Rick", is_active=True,
        )
        # m1 predice al revés del resultado real (est ≠ real); m7 sin
        # predicción.
        for m, home, away in (
            (cls.m1, 0, 1), (cls.m2, 2, 0), (cls.m3, 1, 1),
            (cls.m4, 0, 3), (cls.m5, 2, 2), (cls.m6, 1, 0),
        ):
            Prediction.objects.create(user=cls.user, match=m,
                                      home_goals=home, away_goals=away,
                                      date=now)

    def _standings(self):
        matches = list(
            Match.objects.filter(stage=self.stage).select_related(
                "home_team", "away_team"
            )
        )
        preds = {
            p.match_id: p for p in Prediction.objects.filter(user=self.user)
        }
        return build_group_standings(matches, preds)

    @staticmethod
    def _table(group, variant):
        return next(t for t in group.tables if t.variant == variant)

    @classmethod
    def _rows(cls, group, variant):
        return {r.team.fifa_code: r for r in cls._table(group, variant).rows}

    @classmethod
    def _order(cls, group, variant):
        return [r.team.fifa_code for r in cls._table(group, variant).rows]

    def test_real_counts_only_finished(self):
        rows = self._rows(self._standings()["A"], "real")
        self.assertEqual(
            {c: r.points for c, r in rows.items()},
            {"MEX": 3, "USA": 1, "JAM": 1, "CAN": 0},
        )
        self.assertEqual(self._order(self._standings()["A"], "real"),
                         ["MEX", "USA", "JAM", "CAN"])

    def test_est_uses_predictions_even_on_finished(self):
        rows = self._rows(self._standings()["A"], "est")
        self.assertEqual(
            {c: r.points for c, r in rows.items()},
            {"CAN": 6, "JAM": 4, "USA": 4, "MEX": 2},
        )
        # JAM y USA empatan en pts y DG (+1); el directo decide: USA le
        # ganó 2-0 a JAM (m2), así que va por delante (regla FIFA 2026).
        self.assertEqual(self._order(self._standings()["A"], "est"),
                         ["CAN", "USA", "JAM", "MEX"])

    def test_mix_combines_real_and_predictions(self):
        group = self._standings()["A"]
        rows = self._rows(group, "mix")
        self.assertEqual(
            {c: r.points for c, r in rows.items()},
            {"JAM": 5, "MEX": 5, "CAN": 3, "USA": 2},
        )
        # JAM y MEX empatan a 5; DG decide (+3 vs +2).
        self.assertEqual(self._order(group, "mix"),
                         ["JAM", "MEX", "CAN", "USA"])

    def test_played_is_real_in_all_variants(self):
        group = self._standings()["A"]
        for variant in ("est", "mix", "real"):
            rows = self._rows(group, variant)
            self.assertEqual(
                {c: r.played for c, r in rows.items()},
                {"MEX": 1, "CAN": 1, "USA": 1, "JAM": 1},
                variant,
            )

    def test_cards_are_real_in_all_variants(self):
        group = self._standings()["A"]
        for variant in ("est", "mix", "real"):
            rows = self._rows(group, variant)
            self.assertEqual((rows["MEX"].yellow, rows["MEX"].red), (1, 0))
            self.assertEqual((rows["CAN"].yellow, rows["CAN"].red), (3, 1))
            # m2 sin tarjetas reportadas: None cuenta como 0.
            self.assertEqual((rows["USA"].yellow, rows["USA"].red), (0, 0))

    def test_finished_without_goals_counts_nothing(self):
        rows = self._rows(self._standings()["B"], "real")
        for row in rows.values():
            self.assertEqual((row.points, row.played), (0, 0))

    def test_unpredicted_matches_skip_est(self):
        rows = self._rows(self._standings()["B"], "est")
        self.assertEqual({c: r.points for c, r in rows.items()},
                         {"BRA": 0, "ARG": 0})

    def test_teams_in_mix_order_with_annotations(self):
        group = self._standings()["A"]
        self.assertEqual([t.fifa_code for t in group.teams],
                         ["JAM", "MEX", "CAN", "USA"])
        by_code = {t.fifa_code: t for t in group.teams}
        self.assertEqual(by_code["JAM"].order_mix, 0)
        self.assertEqual(by_code["CAN"].order_est, 0)
        self.assertEqual(by_code["MEX"].order_real, 0)

    def test_groups_do_not_leak(self):
        standings = self._standings()
        self.assertEqual(set(standings), {"A", "B"})
        self.assertEqual(len(self._rows(standings["A"], "real")), 4)
        self.assertEqual(len(self._rows(standings["B"], "real")), 2)
