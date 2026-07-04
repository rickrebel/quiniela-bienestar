"""Tests de ``Window.third_place_multiplier`` y ``multiplier_resolver``.

Cubre que el tercer lugar (``Match.of_number == 103``) pueda pesar distinto
de la final (``104``) aunque compartan ``Stage``/``Window``, que herede el
multiplicador de la ventana cuando el campo queda vacío, y que una ventana
de grupos sin el campo fijado no se vea afectada. Modelado sobre las
fixtures de ``test_penalty_scoring.py`` (Window/Match de eliminatorias con
``of_number``).
"""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from pool.models import Prediction, Quiniela, User, UserQuiniela, Window
from pool.services.evaluation import recompute_all
from tournament.models import Match, Stadium, Stage, Team


class ThirdPlaceMultiplierTests(TestCase):
    """El resolvedor de multiplicador aplica el peso por partido."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_rules", stdout=StringIO())
        cls.quiniela = Quiniela.objects.get(slug="bienestar")
        now = timezone.now()
        cls.group_stage = Stage.objects.create(
            key="GROUP_STAGE", name="Fase de grupos", short_name="grupos",
            color="#4CAF50", order=1, is_group=True,
            send_deadline=now - timedelta(days=1),
        )
        cls.final_stage = Stage.objects.create(
            key="FINAL", name="Final", short_name="final",
            color="#FFC107", order=8, send_deadline=now - timedelta(days=1),
        )
        cls.w_groups = Window.objects.create(
            quiniela=cls.quiniela, order=1, multiplier=Decimal("1"))
        cls.w_groups.stages.add(cls.group_stage)
        cls.w_final = Window.objects.create(
            quiniela=cls.quiniela, order=8, multiplier=Decimal("6"),
            third_place_multiplier=Decimal("3"))
        cls.w_final.stages.add(cls.final_stage)

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
        # Tercer lugar y final: mismo Stage/Window, distinto of_number.
        cls.third_place_match = Match.objects.create(
            datetime=now - timedelta(hours=3), stage=cls.final_stage,
            stadium=cls.stadium, home_team=cls.team_a, away_team=cls.team_b,
            of_number=103, status="FINISHED", home_goals=1, away_goals=0,
            decided_by=Match.REGULAR,
        )
        cls.final_match = Match.objects.create(
            datetime=now - timedelta(hours=1), stage=cls.final_stage,
            stadium=cls.stadium, home_team=cls.team_a, away_team=cls.team_b,
            of_number=104, status="FINISHED", home_goals=2, away_goals=0,
            decided_by=Match.REGULAR,
        )
        cls.group_match = Match.objects.create(
            datetime=now - timedelta(hours=5), stage=cls.group_stage,
            stadium=cls.stadium, home_team=cls.team_a, away_team=cls.team_b,
            of_number=1, status="FINISHED", home_goals=1, away_goals=1,
            decided_by=Match.REGULAR,
        )

    def _predict(self, match, home, away):
        user = User.objects.create_user(
            f"u{Prediction.objects.count()}@x.com", first_name="U",
            is_active=True,
        )
        UserQuiniela.objects.get_or_create(user=user, quiniela=self.quiniela)
        return Prediction.objects.create(
            user=user, quiniela=self.quiniela, match=match,
            home_goals=home, away_goals=away, date=timezone.now(),
        )

    def test_third_place_uses_its_own_multiplier(self):
        # 1-0 exacto: base = 3 (RESULT) + 1 (DIFF) + 1 (EXACT) = 5.
        pred = self._predict(self.third_place_match, 1, 0)
        recompute_all()
        pred.refresh_from_db()
        self.assertEqual(pred.base_points, Decimal("5"))
        self.assertEqual(pred.points, Decimal("15"))  # 5 × 3

    def test_final_uses_window_multiplier(self):
        # 2-0 exacto: mismo base = 5.
        pred = self._predict(self.final_match, 2, 0)
        recompute_all()
        pred.refresh_from_db()
        self.assertEqual(pred.base_points, Decimal("5"))
        self.assertEqual(pred.points, Decimal("30"))  # 5 × 6

    def test_third_place_without_override_inherits_window_multiplier(self):
        self.w_final.third_place_multiplier = None
        self.w_final.save()
        pred = self._predict(self.third_place_match, 1, 0)
        recompute_all()
        pred.refresh_from_db()
        self.assertEqual(pred.points, Decimal("30"))  # 5 × 6, como la final

    def test_group_window_unaffected(self):
        # Empate: base = 3 (RESULT) + 1 (EXACT en empate) = 4, sin bono DIFF.
        pred = self._predict(self.group_match, 1, 1)
        recompute_all()
        pred.refresh_from_db()
        self.assertEqual(pred.base_points, Decimal("4"))
        self.assertEqual(pred.points, Decimal("4"))  # × 1
