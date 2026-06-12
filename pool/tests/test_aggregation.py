"""Tests de la agregación colectiva (media recortada + Poisson)."""

from django.test import SimpleTestCase

from pool.services.aggregation import (
    aggregate_score, poisson_matrix, trimmed_mean)


class TrimmedMeanTests(SimpleTestCase):
    def test_trims_three_per_tail_with_31_values(self):
        # 3 ceros y 3 nueves son justo el 10% por cola: deben caer.
        values = [0] * 3 + [1] * 25 + [9] * 3
        self.assertEqual(trimmed_mean(values), 1.0)

    def test_small_sample_degrades_to_plain_mean(self):
        self.assertEqual(trimmed_mean([1, 2]), 1.5)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            trimmed_mean([])

    def test_unsorted_input(self):
        values = [9, 1, 0, 1, 1, 1, 1, 1, 1, 1]  # 10 valores: recorta 1 y 1
        self.assertEqual(trimmed_mean(values), 1.0)


class PoissonMatrixTests(SimpleTestCase):
    def test_probabilities_sum_to_almost_one(self):
        matrix = poisson_matrix(1.5, 0.8)
        total = sum(sum(row) for row in matrix)
        self.assertAlmostEqual(total, 1.0, places=4)

    def test_lambda_zero_is_certain_zero_goals(self):
        matrix = poisson_matrix(0.0, 0.0)
        self.assertEqual(matrix[0][0], 1.0)


class AggregateScoreTests(SimpleTestCase):
    def test_clear_favorite(self):
        # λ 1.75 vs 0.25: el marcador más probable es 1-0.
        result = aggregate_score([2, 2, 2, 1], [0, 0, 1, 0])
        self.assertEqual((result.home_goals, result.away_goals), (1, 0))

    def test_all_zero_predictions(self):
        result = aggregate_score([0, 0, 0], [0, 0, 0])
        self.assertEqual((result.home_goals, result.away_goals), (0, 0))

    def test_symmetric_input_breaks_tie_toward_home_win(self):
        # λ 1-1: las celdas 0-0, 0-1, 1-0 y 1-1 empatan en e^-2. El
        # desempate por signo descarta los empates (sin bono de
        # diferencia valen menos) y la convención prefiere al local.
        result = aggregate_score([1, 1, 1], [1, 1, 1])
        self.assertEqual((result.home_goals, result.away_goals), (1, 0))

    def test_ranked_is_descending(self):
        result = aggregate_score([2, 1, 2], [1, 0, 1])
        probs = [p for _, _, p in result.ranked]
        self.assertEqual(probs, sorted(probs, reverse=True))
