"""Tests de las reglas de puntuación (ver templates/reglas.html)."""

from django.test import SimpleTestCase

from pool.services.scoring import calculate_points, score_detail


class CalculatePointsTests(SimpleTestCase):
    def test_exact_score_with_winner(self):
        self.assertEqual(calculate_points(2, 1, 2, 1), 5)
        self.assertEqual(calculate_points(0, 3, 0, 3), 5)

    def test_exact_score_draw(self):
        self.assertEqual(calculate_points(1, 1, 1, 1), 4)
        self.assertEqual(calculate_points(0, 0, 0, 0), 4)

    def test_winner_and_goal_difference(self):
        self.assertEqual(calculate_points(3, 2, 2, 1), 4)
        self.assertEqual(calculate_points(0, 2, 1, 3), 4)

    def test_winner_only(self):
        self.assertEqual(calculate_points(1, 0, 3, 1), 3)
        self.assertEqual(calculate_points(0, 1, 1, 4), 3)

    def test_draw_not_exact(self):
        self.assertEqual(calculate_points(1, 1, 2, 2), 3)
        self.assertEqual(calculate_points(3, 3, 0, 0), 3)

    def test_wrong_outcome(self):
        self.assertEqual(calculate_points(2, 0, 0, 2), 0)
        self.assertEqual(calculate_points(1, 0, 0, 1), 0)
        self.assertEqual(calculate_points(1, 1, 2, 1), 0)
        self.assertEqual(calculate_points(2, 1, 1, 1), 0)

    def test_missing_data_returns_none(self):
        self.assertIsNone(calculate_points(None, 1, 2, 1))
        self.assertIsNone(calculate_points(1, None, 2, 1))
        self.assertIsNone(calculate_points(1, 1, None, 1))
        self.assertIsNone(calculate_points(1, 1, 2, None))


class ScoreDetailFlagsTests(SimpleTestCase):
    """Los flags alimentan los chips de la UI; deben ser disjuntos y
    distinguir un 4 exacto-empate de un 4 ganador+diferencia."""

    def test_exact_win_sets_only_exact(self):
        detail = score_detail(2, 1, 2, 1)
        self.assertEqual((detail.points, detail.exact, detail.diff_bonus),
                         (5, True, False))

    def test_exact_draw_sets_only_exact(self):
        detail = score_detail(1, 1, 1, 1)
        self.assertEqual((detail.points, detail.exact, detail.diff_bonus),
                         (4, True, False))

    def test_diff_bonus_without_exact(self):
        detail = score_detail(3, 2, 2, 1)
        self.assertEqual((detail.points, detail.exact, detail.diff_bonus),
                         (4, False, True))

    def test_draw_never_gets_diff_bonus(self):
        detail = score_detail(2, 2, 1, 1)
        self.assertEqual((detail.points, detail.exact, detail.diff_bonus),
                         (3, False, False))

    def test_miss_clears_all_flags(self):
        detail = score_detail(2, 0, 0, 2)
        self.assertEqual((detail.points, detail.exact, detail.diff_bonus),
                         (0, False, False))
