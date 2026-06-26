"""Tests del armado de la tabla de posiciones."""

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from pool.models import Prediction, Quiniela, User, UserQuiniela
from pool.services.evaluation import recompute_all
from pool.services.leaderboard import build_leaderboard
from pool.services.membership import active_quiniela
from tournament.models import Match, Stadium, Stage, Team


def _enroll(user):
    """Inscribe al usuario en bienestar (membresía requerida por el scoring)."""
    UserQuiniela.objects.get_or_create(
        user=user, quiniela=Quiniela.objects.get(slug="bienestar"))
    return user


def _prediction(user, match, home, away):
    _enroll(user)
    return Prediction.objects.create(
        user=user, quiniela=Quiniela.objects.get(slug="bienestar"),
        match=match, home_goals=home, away_goals=away,
        date=timezone.now(),
    )


def evaluated_board():
    """Congela los puntos (como en producción tras una captura) y arma la
    tabla de bienestar: ``build_leaderboard`` ya solo lee lo guardado."""
    recompute_all()
    return build_leaderboard(Quiniela.objects.get(slug="bienestar"))


class BuildLeaderboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_rules")
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

        cls.ana = _enroll(User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True))
        cls.beto = _enroll(User.objects.create_user(
            "beto@x.com", first_name="Beto", is_active=True))
        cls.inactive = User.objects.create_user("nadie@x.com",
                                                first_name="Nadie")

    def test_only_finished_matches_count(self):
        _prediction(self.ana, self.pending, 5, 0)  # no debe sumar
        _prediction(self.ana, self.finished_1, 2, 1)  # exacto: 5

        row = evaluated_board().row_for(self.ana)
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

        row = evaluated_board().row_for(self.ana)
        self.assertEqual(row.points, 8)
        # outcomes no es disjunto: el exacto y la diferencia cuentan ambos.
        self.assertEqual(row.outcomes, 2)
        self.assertEqual(row.exact, 1)
        self.assertEqual(row.diffs, 1)

    def test_tied_users_share_position(self):
        _prediction(self.ana, self.finished_1, 1, 0)   # 3 pts
        _prediction(self.beto, self.finished_1, 1, 0)  # 3 pts

        rows = evaluated_board().rows
        self.assertEqual([r.position for r in rows], [1, 1])

    def test_exact_orders_display_but_not_position(self):
        # Ambos con 4 pts: Ana por empate exacto, Beto por ganador+diferencia.
        # El exacto pone a Ana arriba, pero la posición sale solo de puntos.
        _prediction(self.ana, self.finished_2, 0, 0)
        _prediction(self.beto, self.finished_1, 3, 2)

        rows = evaluated_board().rows
        self.assertEqual(rows[0].user, self.ana)
        self.assertEqual([r.position for r in rows], [1, 1])

    def test_dense_ranking_does_not_skip_positions(self):
        # Dos primeros lugares empatados: el siguiente es 2°, no 3°.
        caro = User.objects.create_user("caro@x.com", first_name="Caro",
                                        is_active=True)
        _prediction(self.ana, self.finished_1, 2, 1)   # 5 pts
        _prediction(self.beto, self.finished_1, 2, 1)  # 5 pts
        _prediction(caro, self.finished_1, 1, 0)       # 3 pts

        rows = evaluated_board().rows
        self.assertEqual([r.position for r in rows], [1, 1, 2])

    def test_inactive_users_excluded_and_idle_users_included(self):
        rows = evaluated_board().rows
        emails = {row.user.email for row in rows}
        self.assertEqual(emails, {"ana@x.com", "beto@x.com"})
        self.assertFalse(any(row.has_played for row in rows))
        self.assertTrue(all(row.points == 0 for row in rows))

    def test_virtual_user_included_despite_inactive(self):
        virtual = _enroll(User.objects.create_user(
            "colectivo@x.com", first_name="Ignorancia colectiva",
            is_virtual=True,
        ))
        self.assertFalse(virtual.is_active)

        rows = evaluated_board().rows
        self.assertIn(virtual, [row.user for row in rows])

    def test_virtual_user_sorts_by_points_but_has_no_position(self):
        virtual = User.objects.create_user(
            "colectivo@x.com", first_name="Ignorancia colectiva",
            is_virtual=True,
        )
        _prediction(self.ana, self.finished_1, 2, 1)      # 5 pts (exacto)
        _prediction(virtual, self.finished_1, 3, 2)       # 4 pts (diferencia)
        _prediction(self.beto, self.finished_1, 3, 1)     # 3 pts (solo resultado)

        rows = evaluated_board().rows
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

        rows = evaluated_board().rows
        self.assertEqual(rows[0].user, virtual)
        self.assertEqual(rows[0].position, 0)
        self.assertEqual(rows[1].user, self.ana)
        self.assertEqual(rows[1].position, 1)

    def test_max_points_sums_only_finished(self):
        # 5 por el 2-1 (ganador) + 4 por el 0-0 (empate); el TIMED no suma.
        self.assertEqual(evaluated_board().max_points, 9)


class LeaderboardTrendTests(TestCase):
    """Flechas de tendencia: 'batch' excluye la última tanda (mismo horario)
    para comparar; 'day' excluye la última jornada (todo el día más reciente,
    en fecha local del estadio)."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_rules")
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
        cls.ana = _enroll(User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True))
        cls.beto = _enroll(User.objects.create_user(
            "beto@x.com", first_name="Beto", is_active=True))

    def _match(self, of_number, dt, home, away):
        return Match.objects.create(
            datetime=dt, stage=self.stage, stadium=self.stadium,
            home_team=self.team_a, away_team=self.team_b, of_number=of_number,
            home_goals=home, away_goals=away, status="FINISHED",
        )

    def _scenario(self):
        """Día 1 (1 tanda) + Día 2 (2 tandas). Ana lidera tras el día 1;
        Beto la supera el día 2 acertando ambos partidos."""
        from datetime import datetime, timezone as dt_tz

        def utc(*args):
            return datetime(*args, tzinfo=dt_tz.utc)

        # Día 1 (local 06-11): m1. Día 2 (local 06-12): m2 (tanda B) y m3
        # (tanda C, la más tardía -> última tanda).
        m1 = self._match(1, utc(2026, 6, 11, 18, 0), 1, 0)
        m2 = self._match(2, utc(2026, 6, 12, 18, 0), 1, 0)
        m3 = self._match(3, utc(2026, 6, 12, 22, 0), 3, 0)

        _prediction(self.ana, m1, 1, 0)   # exacto: 5
        _prediction(self.ana, m2, 5, 5)   # fallo: 0
        _prediction(self.ana, m3, 0, 1)   # fallo: 0

        _prediction(self.beto, m1, 2, 2)  # fallo: 0
        _prediction(self.beto, m2, 1, 0)  # exacto: 5
        _prediction(self.beto, m3, 3, 0)  # exacto: 5
        return m1, m2, m3

    def test_day_baseline_reflects_swap_over_the_last_day(self):
        self._scenario()
        rows = {r.user: r for r in evaluated_board().rows}
        # Antes del día 2: Ana 5 (1°), Beto 0 (2°). Ahora Beto 10 (1°),
        # Ana 5 (2°): Beto sube, Ana baja.
        self.assertEqual(rows[self.beto].trend_day, "up")
        self.assertEqual(rows[self.ana].trend_day, "down")

    def test_batch_baseline_excludes_only_the_last_batch(self):
        self._scenario()
        rows = {r.user: r for r in evaluated_board().rows}
        # Excluyendo solo m3: Ana 5, Beto 5 (empate, ambos 1°). Ahora Beto
        # es 1° y Ana cae a 2°: Ana baja, Beto sin cambio.
        self.assertEqual(rows[self.beto].trend_batch, None)
        self.assertEqual(rows[self.ana].trend_batch, "down")

    def test_no_trend_when_only_one_batch_exists(self):
        # Un solo partido (una tanda, un día): no hay con qué comparar.
        from datetime import datetime, timezone as dt_tz
        m1 = self._match(
            1, datetime(2026, 6, 11, 18, 0, tzinfo=dt_tz.utc), 1, 0,
        )
        _prediction(self.ana, m1, 1, 0)
        rows = {r.user: r for r in evaluated_board().rows}
        self.assertIsNone(rows[self.ana].trend_batch)
        self.assertIsNone(rows[self.ana].trend_day)

    def test_virtual_user_has_no_trend(self):
        virtual = User.objects.create_user(
            "colectivo@x.com", first_name="Ignorancia colectiva",
            is_virtual=True,
        )
        m1, m2, m3 = self._scenario()
        _prediction(virtual, m1, 0, 0)
        _prediction(virtual, m3, 3, 0)
        row = evaluated_board().row_for(virtual)
        self.assertIsNone(row.trend_batch)
        self.assertIsNone(row.trend_day)


class QuinielaScopeTests(TestCase):
    """Cada board es independiente: solo cuenta a los miembros de la
    quiniela y sus predicciones."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_rules")
        cls.bienestar = Quiniela.objects.get(slug="bienestar")
        cls.sanginiela = Quiniela.objects.get(slug="sanginiela")
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
        cls.match = Match.objects.create(
            datetime=timezone.now(), stage=cls.stage, stadium=cls.stadium,
            home_team=cls.team_a, away_team=cls.team_b, of_number=1,
            home_goals=2, away_goals=1, status="FINISHED",
        )

    def _pred(self, user, quiniela, home, away):
        UserQuiniela.objects.get_or_create(user=user, quiniela=quiniela)
        Prediction.objects.create(
            user=user, quiniela=quiniela, match=self.match,
            home_goals=home, away_goals=away, date=timezone.now(),
        )

    def test_board_excludes_other_quinielas_members_and_points(self):
        ana = User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True)
        beto = User.objects.create_user(
            "beto@x.com", first_name="Beto", is_active=True)
        # Ana en bienestar (exacto: 5); Beto solo en sanginiela.
        self._pred(ana, self.bienestar, 2, 1)
        self._pred(beto, self.sanginiela, 2, 1)
        recompute_all()

        bienestar_board = build_leaderboard(self.bienestar)
        self.assertEqual(
            {r.user for r in bienestar_board.rows}, {ana})
        self.assertEqual(bienestar_board.row_for(ana).points, 5)

        sanginiela_board = build_leaderboard(self.sanginiela)
        self.assertEqual(
            {r.user for r in sanginiela_board.rows}, {beto})

    def test_same_user_different_points_per_quiniela(self):
        # La misma usuaria, en ambas quinielas, con pronósticos distintos:
        # cada board la puntúa por su propia predicción.
        ana = User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True)
        self._pred(ana, self.bienestar, 2, 1)   # exacto: 5
        self._pred(ana, self.sanginiela, 3, 1)  # solo resultado: 3
        recompute_all()

        self.assertEqual(
            build_leaderboard(self.bienestar).row_for(ana).points, 5)
        self.assertEqual(
            build_leaderboard(self.sanginiela).row_for(ana).points, 3)


class ActiveQuinielaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_rules")

    def test_returns_first_membership(self):
        user = User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True)
        bienestar = Quiniela.objects.get(slug="bienestar")
        UserQuiniela.objects.create(user=user, quiniela=bienestar)
        self.assertEqual(active_quiniela(user), bienestar)

    def test_none_without_membership(self):
        user = User.objects.create_user(
            "sola@x.com", first_name="Sola", is_active=True)
        self.assertIsNone(active_quiniela(user))
