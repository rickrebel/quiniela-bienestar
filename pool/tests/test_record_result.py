"""Tests del endpoint de captura manual de resultados."""

import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from pool.models import User
from tournament.models import Match, Stadium, Stage, Team

VALID = {
    "home_goals": 2, "away_goals": 1,
    "home_yellow": 1, "away_yellow": 0,
    "home_red": 0, "away_red": 0,
}


class RecordResultTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.group_stage = Stage.objects.create(
            key="GROUP_STAGE", name="Fase de grupos", short_name="grupos",
            color="#4CAF50", order=1, send_deadline=now - timedelta(days=1),
        )
        cls.knockout = Stage.objects.create(
            key="LAST_32", name="Dieciseisavos", short_name="16avos",
            color="#2196F3", order=2, send_deadline=now - timedelta(days=1),
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
        # Empezó hace 3 h: ya pasó la ventana de 105 min.
        cls.group_match = Match.objects.create(
            datetime=now - timedelta(hours=3), stage=cls.group_stage,
            stadium=cls.stadium, home_team=cls.team_a,
            away_team=cls.team_b, of_number=1,
        )
        cls.knockout_match = Match.objects.create(
            datetime=now - timedelta(hours=3), stage=cls.knockout,
            stadium=cls.stadium, home_team=cls.team_a,
            away_team=cls.team_b, of_number=73,
        )
        cls.recorder = User.objects.create_user(
            "rec@x.com", first_name="Rec", is_active=True,
            can_record_results=True,
        )
        cls.player = User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True,
        )

    def _post(self, match, payload, user=None):
        self.client.force_login(user or self.recorder)
        return self.client.post(
            f"/match/{match.id}/result/",
            json.dumps(payload), content_type="application/json",
        )

    def test_requires_permission(self):
        response = self._post(self.group_match, VALID, user=self.player)
        self.assertEqual(response.status_code, 403)

    def test_superuser_without_flag_can_record(self):
        boss = User.objects.create_user(
            "boss@x.com", first_name="Boss", is_active=True,
            is_superuser=True,
        )
        response = self._post(self.group_match, VALID, user=boss)
        self.assertEqual(response.status_code, 200)

    def test_unknown_match_404(self):
        self.client.force_login(self.recorder)
        response = self.client.post(
            "/match/9999/result/", json.dumps(VALID),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_too_early_403(self):
        self.group_match.datetime = timezone.now() - timedelta(minutes=90)
        self.group_match.save(update_fields=["datetime"])
        response = self._post(self.group_match, VALID)
        self.assertEqual(response.status_code, 403)

    def test_already_finished_409(self):
        self.group_match.status = "FINISHED"
        self.group_match.home_goals = 1
        self.group_match.away_goals = 1
        self.group_match.save()
        response = self._post(self.group_match, VALID)
        self.assertEqual(response.status_code, 409)

    def test_rejects_missing_and_invalid_values(self):
        for bad in (
            {**VALID, "home_goals": None},
            {**VALID, "home_goals": -1},
            {**VALID, "home_goals": "2"},
            {**VALID, "home_goals": True},
            {**VALID, "home_penalties": 4},  # penales a medias
        ):
            response = self._post(self.group_match, bad)
            self.assertEqual(response.status_code, 400, bad)

    def test_rejects_penalties_in_group_stage(self):
        payload = {**VALID, "home_goals": 1, "away_goals": 1,
                   "home_penalties": 4, "away_penalties": 3}
        response = self._post(self.group_match, payload)
        self.assertEqual(response.status_code, 400)

    def test_rejects_penalties_without_tie(self):
        payload = {**VALID, "home_penalties": 4, "away_penalties": 3}
        response = self._post(self.knockout_match, payload)
        self.assertEqual(response.status_code, 400)

    def test_knockout_tie_requires_penalties(self):
        payload = {**VALID, "home_goals": 1, "away_goals": 1}
        response = self._post(self.knockout_match, payload)
        self.assertEqual(response.status_code, 400)

    def test_rejects_tied_penalties(self):
        payload = {**VALID, "home_goals": 1, "away_goals": 1,
                   "home_penalties": 4, "away_penalties": 4}
        response = self._post(self.knockout_match, payload)
        self.assertEqual(response.status_code, 400)

    def test_group_stage_happy_path(self):
        response = self._post(self.group_match, VALID)
        self.assertEqual(response.status_code, 200)
        self.group_match.refresh_from_db()
        self.assertEqual(self.group_match.status, "FINISHED")
        self.assertEqual(self.group_match.home_goals, 2)
        self.assertEqual(self.group_match.away_goals, 1)
        self.assertEqual(self.group_match.home_yellow, 1)
        self.assertEqual(self.group_match.decided_by, Match.REGULAR)
        self.assertIsNone(self.group_match.home_penalties)

    def test_knockout_with_penalties_happy_path(self):
        payload = {**VALID, "home_goals": 1, "away_goals": 1,
                   "home_penalties": 4, "away_penalties": 3}
        response = self._post(self.knockout_match, payload)
        self.assertEqual(response.status_code, 200)
        self.knockout_match.refresh_from_db()
        self.assertEqual(self.knockout_match.status, "FINISHED")
        self.assertEqual(self.knockout_match.decided_by,
                         Match.PENALTY_SHOOTOUT)
        self.assertEqual(self.knockout_match.home_penalties, 4)
        self.assertEqual(self.knockout_match.away_penalties, 3)

    def test_recapture_after_success_409(self):
        self._post(self.group_match, VALID)
        response = self._post(self.group_match,
                              {**VALID, "home_goals": 5})
        self.assertEqual(response.status_code, 409)
        self.group_match.refresh_from_db()
        self.assertEqual(self.group_match.home_goals, 2)
