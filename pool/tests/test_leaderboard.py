"""Tests del armado de la tabla de posiciones."""

from django.test import TestCase
from django.utils import timezone

from pool.models import Prediction, User
from pool.services.leaderboard import build_leaderboard
from tournament.models import Match, Stadium, Stage, Team


def _prediction(user, match, home, away):
    return Prediction.objects.create(
        user=user, match=match, home_goals=home, away_goals=away,
        date=timezone.now(),
    )


class BuildLeaderboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stage = Stage.objects.create(
            key="GROUP_STAGE", name="Fase de grupos", short_name="grupos",
            color="#4CAF50", order=1,
        )
        cls.stadium = Stadium.objects.create(
            name="Estadio Azteca", city="CDMX", country="mx", utc_offset=-6,
        )
        cls.team_a = Team.objects.create(
            name="Mexico", name_es="México", fifa_code="MEX", group_name="A",
            confederation="concacaf",
        )
        cls.team_b = Team.objects.create(
            name="Canada", name_es="Canadá", fifa_code="CAN", group_name="A",
            confederation="concacaf",
        )

        def match(of_number, **kwargs):
            return Match.objects.create(
                datetime=timezone.now(), stage=cls.stage, stadium=cls.stadium,
                home_team=cls.team_a, away_team=cls.team_b,
                of_number=of_number, **kwargs,
            )

        cls.finished_1 = match(1, home_goals=2, away_goals=1,
                               status="FINISHED")
        cls.finished_2 = match(2, home_goals=0, away_goals=0,
                               status="FINISHED")
        cls.pending = match(3, status="TIMED")

        cls.ana = User.objects.create_user("ana@x.com", first_name="Ana",
                                           is_active=True)
        cls.beto = User.objects.create_user("beto@x.com", first_name="Beto",
                                            is_active=True)
        cls.inactive = User.objects.create_user("nadie@x.com",
                                                first_name="Nadie")

    def test_only_finished_matches_count(self):
        _prediction(self.ana, self.pending, 5, 0)  # no debe sumar
        _prediction(self.ana, self.finished_1, 2, 1)  # exacto: 5

        row = build_leaderboard().row_for(self.ana)
        self.assertEqual(row.points, 5)
        self.assertEqual(row.outcomes, 1)
        self.assertEqual(row.exact, 1)
        # el exacto no-empate también acertó la diferencia
        self.assertEqual(row.diffs, 1)

    def test_counts_come_from_flags_not_value(self):
        # 4 pts por ganador+diferencia (3-2 vs 2-1) no es un exacto.
        _prediction(self.ana, self.finished_1, 3, 2)
        # 4 pts por empate exacto (0-0) no es bono de diferencia.
        _prediction(self.ana, self.finished_2, 0, 0)

        row = build_leaderboard().row_for(self.ana)
        self.assertEqual(row.points, 8)
        # outcomes no es disjunto: el exacto y la diferencia cuentan ambos.
        self.assertEqual(row.outcomes, 2)
        self.assertEqual(row.exact, 1)
        self.assertEqual(row.diffs, 1)

    def test_tied_users_share_position(self):
        _prediction(self.ana, self.finished_1, 1, 0)   # 3 pts
        _prediction(self.beto, self.finished_1, 1, 0)  # 3 pts

        rows = build_leaderboard().rows
        self.assertEqual([r.position for r in rows], [1, 1])

    def test_exact_orders_display_but_not_position(self):
        # Ambos con 4 pts: Ana por empate exacto, Beto por ganador+diferencia.
        # El exacto pone a Ana arriba, pero la posición sale solo de puntos.
        _prediction(self.ana, self.finished_2, 0, 0)
        _prediction(self.beto, self.finished_1, 3, 2)

        rows = build_leaderboard().rows
        self.assertEqual(rows[0].user, self.ana)
        self.assertEqual([r.position for r in rows], [1, 1])

    def test_dense_ranking_does_not_skip_positions(self):
        # Dos primeros lugares empatados: el siguiente es 2°, no 3°.
        caro = User.objects.create_user("caro@x.com", first_name="Caro",
                                        is_active=True)
        _prediction(self.ana, self.finished_1, 2, 1)   # 5 pts
        _prediction(self.beto, self.finished_1, 2, 1)  # 5 pts
        _prediction(caro, self.finished_1, 1, 0)       # 3 pts

        rows = build_leaderboard().rows
        self.assertEqual([r.position for r in rows], [1, 1, 2])

    def test_inactive_users_excluded_and_idle_users_included(self):
        rows = build_leaderboard().rows
        emails = {row.user.email for row in rows}
        self.assertEqual(emails, {"ana@x.com", "beto@x.com"})
        self.assertFalse(any(row.has_played for row in rows))
        self.assertTrue(all(row.points == 0 for row in rows))

    def test_virtual_user_included_despite_inactive(self):
        virtual = User.objects.create_user(
            "colectivo@x.com", first_name="Ignorancia colectiva",
            is_virtual=True,
        )
        self.assertFalse(virtual.is_active)

        rows = build_leaderboard().rows
        self.assertIn(virtual, [row.user for row in rows])

    def test_virtual_user_sorts_by_points_but_has_no_position(self):
        virtual = User.objects.create_user(
            "colectivo@x.com", first_name="Ignorancia colectiva",
            is_virtual=True,
        )
        _prediction(self.ana, self.finished_1, 2, 1)      # 5 pts (exacto)
        _prediction(virtual, self.finished_1, 3, 2)       # 4 pts (diferencia)
        _prediction(self.beto, self.finished_1, 3, 1)     # 3 pts (solo resultado)

        rows = build_leaderboard().rows
        # Ordenado entre los reales por puntos, pero sin posición y sin
        # recorrer a nadie: Beto sigue siendo 2°.
        self.assertEqual([r.user for r in rows],
                         [self.ana, virtual, self.beto])
        self.assertEqual([r.position for r in rows], [1, 0, 2])

    def test_virtual_user_on_top_does_not_take_first_place(self):
        virtual = User.objects.create_user(
            "colectivo@x.com", first_name="Ignorancia colectiva",
            is_virtual=True,
        )
        _prediction(virtual, self.finished_1, 2, 1)   # 5 pts
        _prediction(self.ana, self.finished_1, 1, 0)  # 3 pts

        rows = build_leaderboard().rows
        self.assertEqual(rows[0].user, virtual)
        self.assertEqual(rows[0].position, 0)
        self.assertEqual(rows[1].user, self.ana)
        self.assertEqual(rows[1].position, 1)

    def test_max_points_sums_only_finished(self):
        # 5 por el 2-1 (ganador) + 4 por el 0-0 (empate); el TIMED no suma.
        self.assertEqual(build_leaderboard().max_points, 9)
