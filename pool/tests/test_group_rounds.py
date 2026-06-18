"""Prueba de la derivación de ronda por grupo (lógica pura, sin BD).

``round_by_match`` no consulta la base: opera sobre objetos con ``id``,
``datetime`` y ``home_team.group_name``. Se simulan con ``SimpleNamespace``
para validar el corte 2+2+2 por orden cronológico, sin importar el orden de
entrada, y el descarte de partidos sin equipo local.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from tournament.services.group_rounds import round_by_match


def _match(mid: int, day: int, group: str | None):
    home = None if group is None else SimpleNamespace(group_name=group)
    return SimpleNamespace(
        id=mid,
        datetime=datetime(2026, 6, day, 12, 0, tzinfo=timezone.utc),
        home_team=home,
    )


class RoundByMatchTests(SimpleTestCase):
    def test_chunks_each_group_into_three_rounds(self) -> None:
        # Grupo A: días 11/11/18/18/24/24 -> rondas 1/1/2/2/3/3.
        days = [11, 11, 18, 18, 24, 24]
        matches = [_match(i, d, "A") for i, d in enumerate(days, start=1)]
        rounds = round_by_match(matches)
        self.assertEqual(
            [rounds[m.id] for m in matches], [1, 1, 2, 2, 3, 3]
        )

    def test_order_independent(self) -> None:
        # Mismo grupo, entrada desordenada: la ronda sigue el calendario.
        a = _match(1, 24, "A")  # ronda 3
        b = _match(2, 11, "A")  # ronda 1
        c = _match(3, 18, "A")  # ronda 2
        d = _match(4, 11, "A")  # ronda 1
        e = _match(5, 24, "A")  # ronda 3
        f = _match(6, 18, "A")  # ronda 2
        rounds = round_by_match([a, b, c, d, e, f])
        self.assertEqual(rounds[2], 1)
        self.assertEqual(rounds[4], 1)
        self.assertEqual(rounds[3], 2)
        self.assertEqual(rounds[6], 2)
        self.assertEqual(rounds[1], 3)
        self.assertEqual(rounds[5], 3)

    def test_groups_are_independent(self) -> None:
        a1 = _match(1, 11, "A")
        b1 = _match(2, 11, "B")
        a2 = _match(3, 18, "A")
        b2 = _match(4, 18, "B")
        rounds = round_by_match([a1, b1, a2, b2])
        self.assertEqual(rounds[1], 1)
        self.assertEqual(rounds[2], 1)
        self.assertEqual(rounds[3], 2)
        self.assertEqual(rounds[4], 2)

    def test_skips_matches_without_home_team(self) -> None:
        placeholder = _match(99, 20, None)
        real = _match(1, 11, "A")
        rounds = round_by_match([placeholder, real])
        self.assertNotIn(99, rounds)
        self.assertEqual(rounds[1], 1)
