"""Tests del anexo C (combinaciones de los 8 mejores terceros)."""

from django.test import SimpleTestCase

from pool.services.anexo_c import WINNER_SLOTS, assign_thirds


class AnexoCTests(SimpleTestCase):
    def test_winner_slots(self):
        self.assertEqual(WINNER_SLOTS, list("ABDEGIKL"))

    def test_known_combination(self):
        # Combinación con los terceros de E..L (verificada contra el HTML).
        mapping = assign_thirds(set("EFGHIJKL"))
        self.assertEqual(mapping, {
            "A": "E", "B": "J", "D": "I", "E": "F",
            "G": "H", "I": "G", "K": "L", "L": "K",
        })

    def test_mapping_covers_eight_slots(self):
        mapping = assign_thirds(set("ABCDEFGH"))
        self.assertIsNotNone(mapping)
        self.assertEqual(set(mapping), set(WINNER_SLOTS))
        # Cada tercero asignado proviene de un grupo clasificado.
        self.assertEqual(set(mapping.values()), set("ABCDEFGH"))

    def test_wrong_size_returns_none(self):
        self.assertIsNone(assign_thirds(set("ABC")))
        self.assertIsNone(assign_thirds(set("ABCDEFGHI")))
