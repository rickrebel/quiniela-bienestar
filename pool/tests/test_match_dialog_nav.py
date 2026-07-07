"""Tests del endpoint de navegación del dialog de partido.

``/<slug>/partido/<id>/dialog/`` devuelve el payload del dialog más los
ids de los vecinos cronológicos globales (orden ``datetime``, ``id``);
en los extremos el vecino es ``None``.
"""

from datetime import datetime, timezone as dt_tz

from django.core.management import call_command
from django.test import TestCase

from pool.models import Quiniela, User, UserQuiniela
from tournament.models import Match, Stadium, Stage, Team


def _utc(*args):
    return datetime(*args, tzinfo=dt_tz.utc)


class MatchDialogNavTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_rules")
        cls.quiniela = Quiniela.objects.get(slug="bienestar")
        stage = Stage.objects.create(
            key="SUBGROUP_1", name="Jornada 1", short_name="J1",
            color="#4CAF50", order=1, is_group=True,
        )
        stadium = Stadium.objects.create(
            name="Azteca", city="CDMX", country="mx", utc_offset=-6,
        )
        home = Team.objects.create(
            name="Mexico", name_es="México", fifa_code="MEX", group_name="A",
            confederation="concacaf", flag_code="mx",
        )
        away = Team.objects.create(
            name="Canada", name_es="Canadá", fifa_code="CAN", group_name="A",
            confederation="concacaf", flag_code="ca",
        )

        def match(of_number, dt):
            return Match.objects.create(
                datetime=dt, stage=stage, stadium=stadium,
                home_team=home, away_team=away, of_number=of_number,
            )

        # m2a y m2b simultáneos: el desempate del orden es por id.
        cls.m1 = match(1, _utc(2026, 6, 11, 18, 0))
        cls.m2a = match(2, _utc(2026, 6, 12, 18, 0))
        cls.m2b = match(3, _utc(2026, 6, 12, 18, 0))
        cls.m3 = match(4, _utc(2026, 6, 13, 18, 0))

        cls.ana = User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True)
        UserQuiniela.objects.get_or_create(
            user=cls.ana, quiniela=cls.quiniela)

    def _get(self, match_id):
        return self.client.get(f"/bienestar/partido/{match_id}/dialog/")

    def test_requires_login(self):
        response = self._get(self.m1.id)
        self.assertEqual(response.status_code, 302)

    def test_middle_match_has_both_neighbors(self):
        self.client.force_login(self.ana)
        data = self._get(self.m2a.id).json()
        self.assertEqual(data["match"]["id"], self.m2a.id)
        self.assertEqual(data["prev_id"], self.m1.id)
        # Empate de datetime: el siguiente es el de id mayor.
        self.assertEqual(data["next_id"], self.m2b.id)

    def test_first_match_has_no_prev(self):
        self.client.force_login(self.ana)
        data = self._get(self.m1.id).json()
        self.assertIsNone(data["prev_id"])
        self.assertEqual(data["next_id"], self.m2a.id)

    def test_last_match_has_no_next(self):
        self.client.force_login(self.ana)
        data = self._get(self.m3.id).json()
        self.assertEqual(data["prev_id"], self.m2b.id)
        self.assertIsNone(data["next_id"])

    def test_unknown_match_404(self):
        self.client.force_login(self.ana)
        self.assertEqual(self._get(999999).status_code, 404)
